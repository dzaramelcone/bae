"""Convention-specific system prompts, regexes, and validation for eval harness.

Six convention candidates tested across Claude model tiers:
- fence_annotation: ```python:exec for executable, plain ```python for illustrative
- wrapper_marker: <exec>```python...```</exec> for executable
- inverse: ```python:example for illustrative, bare ```python remains executable
- xml_tag: <run>code</run> for executable, fences for illustrative
- json_tool: {"execute": "code"} JSON block for executable, fences for illustrative
- yaml_meta: ```python with # %% exec comment for executable
"""

from __future__ import annotations

import asyncio
import json
import os
import re


# ---------------------------------------------------------------------------
# Shared preamble (kept minimal)
# ---------------------------------------------------------------------------

_PREAMBLE = """\
You are the AI inside cortex, a Python REPL. You share a namespace with the user.
Answer in natural language by default. Be concise.
Only your FIRST executable block per response is run."""


# ---------------------------------------------------------------------------
# System prompts -- one per convention, kept lean
# ---------------------------------------------------------------------------

_PROMPT_FENCE_ANNOTATION = _PREAMBLE + """

## Code execution convention
Use `python:exec` for code to run. Use plain `python` for examples.

<examples>
<example>
User: what's 2**100?
Assistant:
```python:exec
2**100
```
</example>
<example>
User: explain how Dep works
Assistant: Dep is a dependency injection marker.
```python
class MyNode(Node):
    val: Annotated[str, Dep(fetch)]
```
</example>
</examples>
"""

_PROMPT_WRAPPER_MARKER = _PREAMBLE + """

## Code execution convention
Wrap executable code in `<exec>` tags. Bare fences are illustrative.

<examples>
<example>
User: what's 2**100?
Assistant:
<exec>
```python
2**100
```
</exec>
</example>
<example>
User: explain how Dep works
Assistant: Dep is a dependency injection marker.
```python
class MyNode(Node):
    val: Annotated[str, Dep(fetch)]
```
</example>
</examples>
"""

_PROMPT_INVERSE = _PREAMBLE + """

## Code execution convention
Bare `python` fences are executed. Tag examples with `python:example` to prevent execution.

<examples>
<example>
User: what's 2**100?
Assistant:
```python
2**100
```
</example>
<example>
User: explain how Dep works
Assistant: Dep is a dependency injection marker.
```python:example
class MyNode(Node):
    val: Annotated[str, Dep(fetch)]
```
</example>
</examples>
"""

_PROMPT_XML_TAG = _PREAMBLE + """

## Code execution convention
Write executable code inside `<run>` tags (no fence needed). Use regular fences for examples.

<examples>
<example>
User: what's 2**100?
Assistant:
<run>
2**100
</run>
</example>
<example>
User: explain how Dep works
Assistant: Dep is a dependency injection marker.
```python
class MyNode(Node):
    val: Annotated[str, Dep(fetch)]
```
</example>
</examples>
"""

_PROMPT_JSON_TOOL = _PREAMBLE + """

## Code execution convention
Write executable code as a JSON block: `{"execute": "code here"}`. Use regular fences for examples.

<examples>
<example>
User: what's 2**100?
Assistant:
{"execute": "print(2**100)"}
</example>
<example>
User: explain how Dep works
Assistant: Dep is a dependency injection marker.
```python
class MyNode(Node):
    val: Annotated[str, Dep(fetch)]
```
</example>
</examples>
"""

_PROMPT_YAML_META = _PREAMBLE + """

## Code execution convention
Start executable code blocks with a `# %% exec` comment on the first line. Fences without this comment are illustrative.

<examples>
<example>
User: what's 2**100?
Assistant:
```python
# %% exec
2**100
```
</example>
<example>
User: explain how Dep works
Assistant: Dep is a dependency injection marker.
```python
class MyNode(Node):
    val: Annotated[str, Dep(fetch)]
```
</example>
</examples>
"""


# ---------------------------------------------------------------------------
# Public dicts keyed by convention name
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS: dict[str, str] = {
    "fence_annotation": _PROMPT_FENCE_ANNOTATION,
    "wrapper_marker": _PROMPT_WRAPPER_MARKER,
    "inverse": _PROMPT_INVERSE,
    "xml_tag": _PROMPT_XML_TAG,
    "json_tool": _PROMPT_JSON_TOOL,
    "yaml_meta": _PROMPT_YAML_META,
}

CONVENTION_REGEXES: dict[str, re.Pattern[str]] = {
    "fence_annotation": re.compile(
        r"```python:exec\s*\n(.*?)\n```",
        re.DOTALL,
    ),
    "wrapper_marker": re.compile(
        r"<exec>\s*```(?:python|py)?\s*\n(.*?)\n```\s*</exec>",
        re.DOTALL,
    ),
    "inverse": re.compile(
        r"```(?:python|py)(?!:example)\s*\n(.*?)\n```",
        re.DOTALL,
    ),
    "xml_tag": re.compile(
        r"<run>\s*\n?(.*?)\n?\s*</run>",
        re.DOTALL,
    ),
    "json_tool": re.compile(
        r'\{"execute":\s*"((?:[^"\\]|\\.)*)"\}',
    ),
    "yaml_meta": re.compile(
        r"```python\s*\n# %% exec\n(.*?)\n```",
        re.DOTALL,
    ),
}

# All python fences regardless of convention (for counting illustrative blocks)
_ALL_PYTHON_RE = re.compile(
    r"```(?:python|py)\S*\s*\n(.*?)\n```",
    re.DOTALL,
)

# Detects python:example fences specifically (for inverse silent-failure check)
_EXAMPLE_FENCE_RE = re.compile(
    r"```python:example\s*\n(.*?)\n```",
    re.DOTALL,
)

# Any code-like content for xml_tag and json_tool (they don't use fences for exec)
_ANY_CODE_RE = re.compile(
    r"(?:```(?:python|py)\S*\s*\n.*?\n```)|(?:<run>.*?</run>)|(?:\{\"execute\":\s*\"(?:[^\"\\]|\\.)*\"\})",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_response(response: str, convention: str, expected: str) -> None:
    """Validate that a model response follows the convention correctly.

    expected types:
      no_code  -- no executable or illustrative code blocks at all
      one_exec -- at least one executable block
      no_exec  -- zero executable blocks, at least one illustrative fence
      mixed    -- at least one executable AND at least one non-executable fence
    """
    regex = CONVENTION_REGEXES[convention]
    exec_blocks = regex.findall(response)
    all_python = _ALL_PYTHON_RE.findall(response)

    if expected == "no_code":
        # For fence-based conventions, check fences. For xml_tag/json_tool, also
        # check their executable patterns.
        if convention in ("xml_tag", "json_tool"):
            any_code = _ANY_CODE_RE.findall(response)
            assert len(any_code) == 0, (
                f"Expected no code blocks, got {len(any_code)}.\n"
                f"Response:\n{response}"
            )
        else:
            assert len(all_python) == 0, (
                f"Expected no code blocks, got {len(all_python)}.\n"
                f"Response:\n{response}"
            )

    elif expected == "one_exec":
        assert len(exec_blocks) >= 1, (
            f"Expected at least one executable block, got none.\n"
            f"Response:\n{response}"
        )

    elif expected == "no_exec":
        assert len(exec_blocks) == 0, (
            f"Expected no executable blocks, got {len(exec_blocks)}.\n"
            f"Response:\n{response}"
        )
        assert len(all_python) >= 1, (
            f"Expected at least one illustrative fence, got none.\n"
            f"Response:\n{response}"
        )
        # Inverse silent-failure detection: verify :example annotation
        if convention == "inverse":
            example_fences = _EXAMPLE_FENCE_RE.findall(response)
            assert len(example_fences) >= 1, (
                f"Inverse convention: expected :example annotation, "
                f"found bare fences (silent compliance failure).\n"
                f"Response:\n{response}"
            )

    elif expected == "mixed":
        assert len(exec_blocks) >= 1, (
            f"Expected at least one executable block, got none.\n"
            f"Response:\n{response}"
        )
        # For xml_tag/json_tool, exec doesn't use fences, so illustrative =
        # any python fence. For fence-based, more fences than exec blocks.
        if convention in ("xml_tag", "json_tool"):
            assert len(all_python) >= 1, (
                f"Expected illustrative fences alongside exec, got none.\n"
                f"Response:\n{response}"
            )
        else:
            assert len(all_python) > len(exec_blocks), (
                f"Expected illustrative blocks beyond exec blocks. "
                f"Total: {len(all_python)}, exec: {len(exec_blocks)}.\n"
                f"Response:\n{response}"
            )

    else:
        raise ValueError(f"Unknown expected type: {expected!r}")


# ---------------------------------------------------------------------------
# Claude CLI dispatcher
# ---------------------------------------------------------------------------

async def eval_send(
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 30,
) -> str:
    """Send a single-shot prompt to Claude CLI and return the response.

    Uses --no-session-persistence to avoid session contention.
    On timeout, retries once before raising.
    """
    cmd = [
        "claude",
        "-p", user_prompt,
        "--model", model,
        "--output-format", "text",
        "--tools", "",
        "--strict-mcp-config",
        "--setting-sources", "",
        "--no-session-persistence",
        "--system-prompt", system_prompt,
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    for attempt in range(2):
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            if attempt == 0:
                continue  # retry once
            raise RuntimeError(
                f"eval_send timed out after {timeout}s on both attempts "
                f"(model={model})"
            )

        if process.returncode != 0:
            stderr = stderr_bytes.decode()
            raise RuntimeError(f"Claude CLI failed (rc={process.returncode}): {stderr}")

        return stdout_bytes.decode().strip()

    # Unreachable, but satisfies type checker
    raise RuntimeError("eval_send: exhausted retries")
