"""Core agent loop -- multi-turn eval decoupled from REPL concerns.

Extracts executable <run> blocks from LM responses, executes Python,
feeds output back. Powers both the REPL AI wrapper and headless
AgenticBackend.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import traceback
from collections.abc import Awaitable, Callable
from io import StringIO




_EXEC_BLOCK_RE = re.compile(
    r"<run>\s*\n?(.*?)\n?\s*</run>",
    re.DOTALL,
)

_AGENT_SYSTEM_PROMPT = (
    "You are a research agent. Use Python code in <run> tags to gather "
    "information. Write working code that produces output."
)


def extract_executable(text: str) -> tuple[str | None, int]:
    """Extract first executable <run> block and count of extras.

    Returns (code, extra_count) where code is the first executable
    block or None, and extra_count is additional blocks ignored.
    """
    matches = _EXEC_BLOCK_RE.findall(text)
    if not matches:
        return None, 0
    return matches[0], len(matches) - 1


async def agent_loop(
    prompt: str,
    *,
    send: Callable[[str], Awaitable[str]],
    namespace: dict,
    max_iters: int = 10,
) -> str:
    """Multi-turn eval loop: prompt -> response -> extract <run> -> execute -> loop.

    Calls send(prompt) to get initial response, then extracts and executes
    <run> blocks, feeding output back until no blocks remain or max_iters
    is reached.

    Args:
        prompt: Initial prompt to send.
        send: Async callable that sends prompt text and returns response text.
        namespace: Python namespace for code execution.
        max_iters: Maximum eval iterations (0 = unlimited).

    Returns:
        Final response text after all code blocks are resolved.
    """
    response = await send(prompt)

    iters = 0
    while not max_iters or iters < max_iters:
        iters += 1

        code, extra = extract_executable(response)
        if code is None:
            break

        # Execute the block
        from bae.repl.exec import async_exec

        output = ""
        try:
            result, captured = await async_exec(code, namespace)
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

        # No-output with no extra blocks: nothing to feed back
        if output == "(no output)" and extra == 0:
            break

        # Build feedback
        feedback = f"[Output]\n{output}"
        if extra > 0:
            feedback += (
                f"\n\nOnly your first executable block was run. "
                f"{extra} additional block{'s' if extra != 1 else ''} "
                f"{'were' if extra != 1 else 'was'} ignored."
            )

        response = await send(feedback)

    return response


def _agent_namespace() -> dict:
    """Fresh namespace for headless agent execution -- no REPL state."""
    import json as _json
    import re as _re
    from pathlib import Path

    return {
        "__builtins__": __builtins__,
        "json": _json,
        "re": _re,
        "os": os,
        "Path": Path,
    }


async def _cli_send(
    prompt: str,
    *,
    model: str,
    session_id: str,
    call_count: int,
    timeout: int = 60,
) -> str:
    """Send prompt to Claude CLI subprocess with session persistence.

    On call_count == 0: starts new session with --session-id and
    --system-prompt. On subsequent calls: resumes with --resume.
    Sanitizes env (strips CLAUDECODE). Returns response text.

    Raises RuntimeError on subprocess failure.
    """
    cmd = [
        "claude",
        "-p", prompt,
        "--model", model,
        "--output-format", "text",
        "--tools", "",
        "--strict-mcp-config",
        "--setting-sources", "",
    ]

    if call_count == 0:
        cmd += ["--session-id", session_id,
                "--system-prompt", _AGENT_SYSTEM_PROMPT]
    else:
        cmd += ["--resume", session_id]

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        start_new_session=True,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        raise RuntimeError(f"CLI send timed out after {timeout}s")

    if process.returncode != 0:
        raise RuntimeError(f"CLI send failed: {stderr_bytes.decode()}")

    return stdout_bytes.decode().strip()
