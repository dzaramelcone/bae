"""AI agent for natural language interaction in cortex.

Uses Claude CLI subprocess with session persistence for conversation.
Eval loop: extract code from AI response, execute, feed results back.
Delegates fill/choose_type to bae's LM protocol.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import traceback
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from bae.repl.exec import async_exec

if TYPE_CHECKING:
    from bae.lm import LM
    from bae.node import Node
    from bae.repl.channels import ChannelRouter
    from bae.repl.store import SessionStore
    from bae.repl.tasks import TaskManager

_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```",
    re.DOTALL,
)

MAX_CONTEXT_CHARS = 2000
_PROMPT_FILE = Path(__file__).parent / "ai_prompt.md"


class AI:
    """AI agent for natural language interaction with bae.

    await ai("question")                  -- NL conversation with context
    await ai.fill(NodeClass, context)     -- populate node via LM
    await ai.choose_type([A, B], context) -- pick successor type via LM
    ai.extract_code(text)                 -- extract python code blocks
    """

    def __init__(
        self,
        *,
        lm: LM,
        router: ChannelRouter,
        namespace: dict,
        tm: TaskManager | None = None,
        store: SessionStore | None = None,
        label: str = "1",
        model: str = "claude-sonnet-4-20250514",
        timeout: int = 60,
        max_eval_iters: int = 5,
    ) -> None:
        self._lm = lm
        self._router = router
        self._namespace = namespace
        self._tm = tm
        self._store = store
        self._label = label
        self._model = model
        self._timeout = timeout
        self._max_eval_iters = max_eval_iters
        self._session_id = str(uuid.uuid4())
        self._call_count = 0

    async def __call__(self, prompt: str) -> str:
        """NL conversation with eval loop: respond -> extract code -> execute -> feed back.

        Extracts Python code blocks from AI responses, executes them in the
        REPL namespace, and feeds results back as the next prompt. Loops
        until no code blocks remain or max_eval_iters is reached.
        """
        parts: list[str] = []
        if self._call_count == 0 and self._store is not None:
            cross = self._store.cross_session_context()
            if cross:
                parts.append(cross)
        context = _build_context(self._namespace)
        if context:
            parts.append(context)
        parts.append(prompt)
        full_prompt = "\n\n".join(parts)

        response = await self._send(full_prompt)
        await asyncio.sleep(0)  # cancellation checkpoint
        self._router.write("ai", response, mode="NL", metadata={"type": "response", "label": self._label})

        for _ in range(self._max_eval_iters):
            blocks = self.extract_code(response)
            if not blocks:
                break

            results = []
            for code in blocks:
                try:
                    result, captured = await async_exec(code, self._namespace)
                    if asyncio.iscoroutine(result):
                        result = await result
                    output = captured
                    if result is not None:
                        output += repr(result)
                    results.append(output or "(no output)")
                except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                    raise
                except BaseException:
                    results.append(traceback.format_exc())
                self._router.write("py", code, mode="PY", metadata={"type": "ai_exec", "label": self._label})

            feedback = "\n".join(f"[Block {i+1} output]\n{r}" for i, r in enumerate(results))
            await asyncio.sleep(0)  # cancellation checkpoint
            response = await self._send(feedback)
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

    async def fill(self, target: type[Node], context: dict | None = None) -> Node:
        """Populate a node's plain fields via bae's LM fill."""
        return await self._lm.fill(target, context or {}, target.__name__)

    async def choose_type(
        self, types: list[type[Node]], context: dict | None = None,
    ) -> type[Node]:
        """Pick successor type from candidates via bae's LM choose_type."""
        return await self._lm.choose_type(types, context or {})

    @staticmethod
    def extract_code(text: str) -> list[str]:
        """Extract Python code blocks from markdown-fenced text."""
        return _CODE_BLOCK_RE.findall(text)

    def __repr__(self) -> str:
        sid = self._session_id[:8]
        n = self._call_count
        return f"ai:{self._label} -- await ai('question'). session {sid}, {n} calls."


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

    # User variables (skip internals, modules, bae types)
    _SKIP = {
        "__builtins__", "ai", "ns", "store", "channels",
        "Node", "Graph", "Dep", "Recall", "GraphResult",
        "LM", "NodeConfig", "Annotated", "asyncio", "os",
    }
    user_vars: list[str] = []
    for name, obj in sorted(namespace.items()):
        if name.startswith("_") or name in _SKIP:
            continue
        if inspect.ismodule(obj):
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
