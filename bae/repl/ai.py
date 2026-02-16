"""AI agent for natural language interaction in cortex.

Uses Claude CLI subprocess with session persistence for conversation.
Eval loop: extract executable <run> blocks from AI response, execute
the first one, feed results back. Delegates fill/choose_type to bae's
LM protocol.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import sys
import traceback
import uuid
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

from bae.agent import extract_executable
from bae.repl.exec import async_exec

if TYPE_CHECKING:
    from bae.lm import LM
    from bae.node import Node
    from bae.repl.channels import ChannelRouter
    from bae.repl.resource import ResourceRegistry
    from bae.repl.tasks import TaskManager
    from bae.repl.tools import ToolRouter

_EXEC_BLOCK_RE = re.compile(
    r"<run>\s*\n?(.*?)\n?\s*</run>",
    re.DOTALL,
)

from bae.repl.spaces.home.service import (
    _exec_read,
    _exec_write,
    _exec_edit_read,
    _exec_edit_replace,
    _exec_glob,
    _exec_grep,
    _MAX_TOOL_OUTPUT,
    _LINE_RANGE_RE,
)

_TOOL_TAG_RE = re.compile(
    r"^[ \t]*<(R|Read|E|Edit|G|Glob|Grep):([^>]+)>\s*$",
    re.MULTILINE | re.IGNORECASE,
)

_WRITE_TAG_RE = re.compile(
    r"^[ \t]*<(W|Write):([^>]+)>\s*\n(.*?)\n[ \t]*</(W|Write)>",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)

_EDIT_REPLACE_RE = re.compile(
    r"^[ \t]*<(E|Edit):([^:>]+):(\d+)-(\d+)>\s*\n(.*?)\n[ \t]*</(E|Edit)>",
    re.DOTALL | re.MULTILINE | re.IGNORECASE,
)

# OSC 8 hyperlink: \033]8;params;ToolName:args\033\\ or \007
_OSC8_TOOL_RE = re.compile(
    r"\033\]8;[^;]*;(Read|Write|Edit|Glob|Grep|R|W|E|G):([^\033\007]+)(?:\033\\|\007)",
    re.IGNORECASE,
)

MAX_CONTEXT_CHARS = 2000
_PROMPT_FILE = Path(__file__).parent / "ai_prompt.md"


class AI:
    """AI agent for natural language interaction with bae.

    await ai("question")                  -- NL conversation with context
    await ai.fill(NodeClass, context)     -- populate node via LM
    await ai.choose_type([A, B], context) -- pick successor type via LM
    ai.extract_executable(text)           -- extract first <run> block
    """

    def __init__(
        self,
        *,
        lm: LM,
        router: ChannelRouter,
        namespace: dict,
        tm: TaskManager | None = None,
        label: str = "1",
        model: str = "claude-sonnet-4-20250514",
        timeout: int = 60,
        max_eval_iters: int = 0,
        tool_router: ToolRouter | None = None,
        registry: ResourceRegistry | None = None,
    ) -> None:
        self._lm = lm
        self._router = router
        self._namespace = namespace
        self._tm = tm
        self._label = label
        self._model = model
        self._timeout = timeout
        self._max_eval_iters = max_eval_iters
        self._tool_router = tool_router
        self._registry = registry
        self._session_id = str(uuid.uuid4())
        self._call_count = 0

    async def __call__(self, prompt: str) -> str:
        """NL conversation with eval loop: respond -> extract code -> execute -> feed back.

        Extracts Python code blocks from AI responses, executes them in the
        REPL namespace, and feeds results back as the next prompt. Loops
        until no code blocks remain. Set max_eval_iters > 0 to cap iterations.
        """
        parts: list[str] = []
        context = _build_context(self._namespace)
        if context:
            parts.append(context)
        parts.append(prompt)
        full_prompt = "\n\n".join(parts)

        response = await self._send(self._with_location(full_prompt))
        await asyncio.sleep(0)  # cancellation checkpoint
        self._router.write("ai", response, mode="NL", metadata={"type": "response", "label": self._label})

        _iters = 0
        while not self._max_eval_iters or _iters < self._max_eval_iters:
            _iters += 1
            # Tool call tags take precedence over <run> blocks
            tool_results = run_tool_calls(response, router=self._tool_router)
            if tool_results:
                all_outputs = []
                for tag, output in tool_results:
                    summary = _tool_summary(tag, output)
                    self._router.write("py", tag, mode="PY",
                        metadata={"type": "tool_translated", "label": self._label,
                                  "tool_summary": summary})
                    all_outputs.append(output)

                combined = "\n---\n".join(all_outputs)
                feedback = f"[Tool output]\n{combined}"
                await asyncio.sleep(0)  # cancellation checkpoint
                response = await self._send(self._with_location(feedback))
                await asyncio.sleep(0)  # cancellation checkpoint
                self._router.write("ai", response, mode="NL",
                    metadata={"type": "response", "label": self._label})
                continue

            # Check for <run> blocks
            blocks = self.extract_executable(response)
            if not blocks:
                break

            # Execute all blocks sequentially
            outputs: list[str] = []
            for code in blocks:
                output = ""
                try:
                    result, captured = await async_exec(code, self._namespace)
                    if asyncio.iscoroutine(result):
                        buf = StringIO()
                        old = sys.stdout
                        sys.stdout = buf
                        try:
                            result = await result
                        finally:
                            sys.stdout = old
                        captured += buf.getvalue()
                    output = captured
                    if result is not None:
                        output += repr(result)
                    output = output or "(no output)"
                except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                    raise
                except BaseException:
                    output = traceback.format_exc()

                self._router.write("py", code, mode="PY", metadata={"type": "ai_exec", "label": self._label})
                if output:
                    self._router.write("py", output, mode="PY", metadata={"type": "ai_exec_result", "label": self._label})
                outputs.append(output)

            combined = "\n---\n".join(outputs)

            # All no-output: nothing to feed back
            if all(o == "(no output)" for o in outputs):
                break

            feedback = f"[Output]\n{combined}"

            await asyncio.sleep(0)  # cancellation checkpoint
            response = await self._send(self._with_location(feedback))
            await asyncio.sleep(0)  # cancellation checkpoint
            self._router.write("ai", response, mode="NL", metadata={"type": "response", "label": self._label})

        return response

    async def _send(self, prompt: str) -> str:
        """Send a prompt to Claude CLI and return the response string.

        Handles command building, env setup, subprocess exec, timeout,
        cancellation, error handling, and call count tracking.
        """
        cmd = [
            "claude",
            "-p", prompt,
            "--model", self._model,
            "--output-format", "text",
            "--tools", "",
            "--strict-mcp-config",
            "--setting-sources", "",
        ]

        if self._call_count == 0:
            cmd += ["--session-id", self._session_id,
                    "--system-prompt", _load_prompt()]
        else:
            cmd += ["--resume", self._session_id]

        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        if self._tm is not None:
            self._tm.register_process(process)
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            raise RuntimeError(f"AI timed out after {self._timeout}s")
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            self._reset_session()
            raise

        if process.returncode != 0:
            stderr = stderr_bytes.decode()
            if "already in use" in stderr:
                self._reset_session()
            raise RuntimeError(f"AI failed: {stderr}")

        response = stdout_bytes.decode().strip()
        self._call_count += 1
        return response

    def _reset_session(self) -> None:
        """Start a fresh CLI session after cancellation or lock error."""
        self._session_id = str(uuid.uuid4())
        self._call_count = 0

    def _with_location(self, prompt: str) -> str:
        """Prepend resource context to prompt."""
        if self._registry is None:
            return prompt
        if self._registry.current is None:
            orientation = self._registry._build_orientation()
            return f"[Location: home]\n{orientation}\n\n{prompt}"
        return f"[Location: {self._registry.breadcrumb()}]\n{prompt}"

    async def fill(self, target: type[Node], context: dict | None = None) -> Node:
        """Populate a node's plain fields via bae's LM fill."""
        return await self._lm.fill(target, context or {}, target.__name__)

    async def choose_type(
        self, types: list[type[Node]], context: dict | None = None,
    ) -> type[Node]:
        """Pick successor type from candidates via bae's LM choose_type."""
        return await self._lm.choose_type(types, context or {})

    @staticmethod
    def extract_executable(text: str) -> list[str]:
        """Extract all executable <run> blocks from text."""
        return extract_executable(text)

    def __repr__(self) -> str:
        sid = self._session_id[:8]
        n = self._call_count
        return f"ai:{self._label} -- await ai('question'). session {sid}, {n} calls."


_TOOL_NAMES = {
    "r": "R", "read": "R",
    "w": "W", "write": "W",
    "e": "E", "edit": "E",
    "g": "G", "glob": "G",
    "grep": "Grep",
}

_TOOL_EXEC = {
    "R": _exec_read,
    "E": _exec_edit_read,
    "G": _exec_glob,
    "Grep": _exec_grep,
}

# Mapping from normalized tool name to router dispatch name
_TOOL_DISPATCH = {
    "R": "read",
    "W": "write",
    "E": "edit",
    "G": "glob",
    "Grep": "grep",
}


def _tool_summary(tag: str, output: str) -> str:
    """Human-readable one-liner summarizing a tool call result.

    Parses the tag format <TYPE:arg> to determine tool kind,
    then generates a concise summary (read/glob/grep get counts,
    write/edit pass output through as-is).
    """
    # Extract TYPE and arg from <TYPE:arg>
    m = re.match(r"<(\w+):(.+?)>", tag.strip())
    if not m:
        return output
    tool_type = _TOOL_NAMES.get(m.group(1).lower(), m.group(1))
    arg = m.group(2).strip()

    if tool_type == "R":
        n = output.count("\n") + 1 if output else 0
        return f"read {arg} ({n} lines)"
    if tool_type == "G":
        lines = output.splitlines()
        n = len(lines) if output and output != "(no matches)" else 0
        return f"glob {arg} ({n} matches)"
    if tool_type == "Grep":
        lines = output.splitlines()
        n = len(lines) if output and output != "(no matches)" else 0
        return f"grep {arg} ({n} matches)"
    # W and E: output is already concise (e.g. "Wrote 42 chars to foo.py")
    return output


def run_tool_calls(text: str, *, router: ToolRouter | None = None) -> list[tuple[str, str]]:
    """Detect and execute ALL tool call tags in prose.

    Returns list of (description, output) pairs. Empty list if no tags found.
    Skips tags inside <run>...</run> blocks or markdown fences.

    Accepts case-insensitive tags, full word variants (Read, Write, Edit,
    Glob, Grep), and OSC 8 hyperlink-wrapped tool calls.

    When router is provided, dispatches through ToolRouter instead of
    calling _exec_* functions directly.
    """
    # Strip executable and illustrative blocks before scanning
    prose = _EXEC_BLOCK_RE.sub("", text)
    prose = re.sub(r"```.*?```", "", prose, flags=re.DOTALL)

    # Collect (position, tag_text, callable) triples
    pending: list[tuple[int, str, object]] = []
    consumed: set[int] = set()

    # Write tags (group 2=filepath, group 3=content)
    for wm in _WRITE_TAG_RE.finditer(prose):
        tag = wm.group(0).split("\n", 1)[0].strip()
        if router:
            pending.append((wm.start(), tag,
                            lambda fp=wm.group(2), c=wm.group(3): router.dispatch("write", fp, content=c)))
        else:
            pending.append((wm.start(), tag,
                            lambda fp=wm.group(2), c=wm.group(3): _exec_write(fp, c)))
        consumed.update(range(wm.start(), wm.end()))

    # Edit-with-replacement (group 2=filepath, 3=start, 4=end, 5=content)
    for em in _EDIT_REPLACE_RE.finditer(prose):
        tag = em.group(0).split("\n", 1)[0].strip()
        if router:
            pending.append((em.start(), tag,
                            lambda fp=em.group(2), s=int(em.group(3)),
                            e=int(em.group(4)), c=em.group(5): router.dispatch("edit", fp, start=s, end=e, content=c)))
        else:
            pending.append((em.start(), tag,
                            lambda fp=em.group(2), s=int(em.group(3)),
                            e=int(em.group(4)), c=em.group(5): _exec_edit_replace(fp, s, e, c)))
        consumed.update(range(em.start(), em.end()))

    # Single-line tags
    for m in _TOOL_TAG_RE.finditer(prose):
        if m.start() in consumed:
            continue
        tool = _TOOL_NAMES.get(m.group(1).lower())
        if router and tool:
            dispatch_name = _TOOL_DISPATCH.get(tool)
            if dispatch_name:
                tag = m.group(0).strip()
                pending.append((m.start(), tag,
                                lambda d=dispatch_name, a=m.group(2): router.dispatch(d, a)))
        else:
            fn = _TOOL_EXEC.get(tool) if tool else None
            if fn:
                tag = m.group(0).strip()
                pending.append((m.start(), tag,
                                lambda f=fn, a=m.group(2): f(a)))

    # OSC 8 hyperlink-wrapped tool calls
    for m in _OSC8_TOOL_RE.finditer(prose):
        if m.start() in consumed:
            continue
        tool = _TOOL_NAMES.get(m.group(1).lower())
        if router and tool:
            dispatch_name = _TOOL_DISPATCH.get(tool)
            if dispatch_name:
                tag = f"<{m.group(1)}:{m.group(2)}>"
                pending.append((m.start(), tag,
                                lambda d=dispatch_name, a=m.group(2): router.dispatch(d, a)))
        else:
            fn = _TOOL_EXEC.get(tool) if tool else None
            if fn:
                tag = f"<{m.group(1)}:{m.group(2)}>"
                pending.append((m.start(), tag,
                                lambda f=fn, a=m.group(2): f(a)))

    # Execute in order
    pending.sort(key=lambda x: x[0])
    results: list[tuple[str, str]] = []
    for _, tag, fn in pending:
        try:
            output = fn()
        except Exception as exc:
            output = f"{type(exc).__name__}: {exc}"
        results.append((tag, output))
    return results


def _load_prompt() -> str:
    """Load the system prompt from ai_prompt.md."""
    return _PROMPT_FILE.read_text()


def _build_context(namespace: dict) -> str:
    """Summarize namespace as REPL state, truncated to MAX_CONTEXT_CHARS.

    Formatted as Python REPL output so the AI sees it as live state
    it's already working with, not abstract metadata.
    """
    from bae.graph import Graph
    from bae.node import Node
    from bae.repl.spaces import ResourceHandle

    lines: list[str] = []

    # Graph topology
    graph = namespace.get("graph")
    if isinstance(graph, Graph):
        lines.append(f">>> ns(graph)")
        lines.append(f"Graph(start={graph.start.__name__})")
        lines.append(f"  Nodes: {len(graph.nodes)}")
        for n in sorted(graph.nodes, key=lambda x: x.__name__):
            succs = graph.edges.get(n, set())
            target = ", ".join(s.__name__ for s in succs) if succs else "(terminal)"
            lines.append(f"    {n.__name__} -> {target}")

    # Recent trace (last 5)
    trace = namespace.get("_trace")
    if isinstance(trace, list) and trace:
        lines.append(f">>> _trace[-{min(5, len(trace))}:]")
        for i, n in enumerate(trace[-5:]):
            lines.append(f"  {i+1}. {type(n).__name__}")

    # User variables (skip internals, modules, bae types, resource navigation)
    _SKIP = {
        "__builtins__", "ai", "ns", "store", "channels",
        "Node", "Graph", "Dep", "Recall", "GraphResult",
        "LM", "NodeConfig", "Annotated", "asyncio", "os",
        "home", "back",
    }
    user_vars: list[str] = []
    for name, obj in sorted(namespace.items()):
        if name.startswith("_") or name in _SKIP:
            continue
        if inspect.ismodule(obj):
            continue
        if isinstance(obj, ResourceHandle):
            continue
        if isinstance(obj, type) and issubclass(obj, Node):
            user_vars.append(f"  {name}  class  {obj.__name__}")
        elif isinstance(obj, Node):
            user_vars.append(f"  {name}  {type(obj).__name__}")
        elif isinstance(obj, Graph):
            continue  # Already shown above
        elif not callable(obj):
            r = repr(obj)
            if len(r) > 60:
                r = r[:57] + "..."
            user_vars.append(f"  {name}  {type(obj).__name__}  {r}")
    if user_vars:
        lines.append(">>> ns()")
        lines.extend(user_vars)

    if not lines:
        return ""

    result = "[REPL state]\n" + "\n".join(lines)
    if len(result) > MAX_CONTEXT_CHARS:
        result = result[:MAX_CONTEXT_CHARS] + "\n  ... (truncated)"
    return result
