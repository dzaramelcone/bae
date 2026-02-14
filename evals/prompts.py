"""Convention-specific system prompts, regexes, and validation for eval harness.

Three convention candidates tested across Claude model tiers:
- fence_annotation: ```python:exec for executable, plain ```python for illustrative
- wrapper_marker: <exec>```python...```</exec> for executable
- inverse: ```python:example for illustrative, bare ```python remains executable
"""

from __future__ import annotations

import asyncio
import os
import re


# ---------------------------------------------------------------------------
# System prompts -- one per convention candidate
# ---------------------------------------------------------------------------

_PROMPT_FENCE_ANNOTATION = """\
# Session
You are the AI inside cortex, a Python REPL. You share a namespace with the user.

## Rules
- Answer in natural language by default. Be concise.
- Reference the namespace state directly.

## Code execution convention
Every Python code fence you write is either EXECUTABLE or ILLUSTRATIVE.
- EXECUTABLE: Code that should run in the REPL. Use `python:exec` annotation on the fence.
- ILLUSTRATIVE: Examples, pseudocode, explanations. Use plain `python` annotation on the fence.

Only your FIRST executable block per response is run. Additional executable blocks are ignored.

Never use the `python:exec` annotation in illustrative code, even when explaining how the convention works.

<examples>
<example>
User: what's 2**100?
Assistant:
```python:exec
2**100
```
</example>

<example>
User: explain how Dep works with an example
Assistant: Dep is a marker for field-level dependency injection. When a Node field is annotated with Dep(fn), the graph resolves and injects the dependency before the node executes.

Here's what it looks like:
```python
# Illustrative -- how Dep is used in a Node definition
class WeatherNode(Node):
    forecast: Annotated[str, Dep(get_forecast)]
```
</example>

<example>
User: show me my variables and explain what ns() does
Assistant: `ns()` lists all namespace objects with types and summaries. Let me show you:
```python:exec
ns()
```

The function inspects every non-underscore entry in the namespace and prints a formatted table:
```python
# How ns() works internally (illustrative)
for name, obj in sorted(namespace.items()):
    if not name.startswith("_"):
        print(f"{name}  {type(obj).__name__}")
```
</example>

<example>
User: what is a Graph in bae?
Assistant: A Graph is a directed agent graph built from Node type hints. It routes execution through nodes based on type annotations, with each node producing a typed output that determines the next node.
</example>
</examples>

## Tools
- `ns()` list all namespace objects with types.
    `ns(obj)` deep-inspect any object.
- Python interpreter: define classes, call functions, import modules.
"""

_PROMPT_WRAPPER_MARKER = """\
# Session
You are the AI inside cortex, a Python REPL. You share a namespace with the user.

## Rules
- Answer in natural language by default. Be concise.
- Reference the namespace state directly.

## Code execution convention
Every Python code fence you write is either EXECUTABLE or ILLUSTRATIVE.
- EXECUTABLE: Code that should run in the REPL. Wrap the entire code fence in `<exec>` tags.
- ILLUSTRATIVE: Examples, pseudocode, explanations. Write a bare code fence with no wrapper.

Only your FIRST executable block per response is run. Additional executable blocks are ignored.

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
User: explain how Dep works with an example
Assistant: Dep is a marker for field-level dependency injection. When a Node field is annotated with Dep(fn), the graph resolves and injects the dependency before the node executes.

Here's what it looks like:
```python
# Illustrative -- how Dep is used in a Node definition
class WeatherNode(Node):
    forecast: Annotated[str, Dep(get_forecast)]
```
</example>

<example>
User: show me my variables and explain what ns() does
Assistant: `ns()` lists all namespace objects with types and summaries. Let me show you:
<exec>
```python
ns()
```
</exec>

The function inspects every non-underscore entry in the namespace and prints a formatted table:
```python
# How ns() works internally (illustrative)
for name, obj in sorted(namespace.items()):
    if not name.startswith("_"):
        print(f"{name}  {type(obj).__name__}")
```
</example>

<example>
User: what is a Graph in bae?
Assistant: A Graph is a directed agent graph built from Node type hints. It routes execution through nodes based on type annotations, with each node producing a typed output that determines the next node.
</example>
</examples>

## Tools
- `ns()` list all namespace objects with types.
    `ns(obj)` deep-inspect any object.
- Python interpreter: define classes, call functions, import modules.
"""

_PROMPT_INVERSE = """\
# Session
You are the AI inside cortex, a Python REPL. You share a namespace with the user.

## Rules
- Answer in natural language by default. Be concise.
- Reference the namespace state directly.

## Code execution convention
Every Python code fence you write is either EXECUTABLE or ILLUSTRATIVE.
- EXECUTABLE: A bare `python` fence (no annotation). This code runs in the REPL.
- ILLUSTRATIVE: Examples, pseudocode, explanations. Use `python:example` annotation on the fence so it does NOT execute.

You MUST annotate every illustrative code fence with `python:example`. A bare `python` fence is always executed.

Only your FIRST executable block per response is run. Additional executable blocks are ignored.

<examples>
<example>
User: what's 2**100?
Assistant:
```python
2**100
```
</example>

<example>
User: explain how Dep works with an example
Assistant: Dep is a marker for field-level dependency injection. When a Node field is annotated with Dep(fn), the graph resolves and injects the dependency before the node executes.

Here's what it looks like:
```python:example
# Illustrative -- how Dep is used in a Node definition
class WeatherNode(Node):
    forecast: Annotated[str, Dep(get_forecast)]
```
</example>

<example>
User: show me my variables and explain what ns() does
Assistant: `ns()` lists all namespace objects with types and summaries. Let me show you:
```python
ns()
```

The function inspects every non-underscore entry in the namespace and prints a formatted table:
```python:example
# How ns() works internally (illustrative)
for name, obj in sorted(namespace.items()):
    if not name.startswith("_"):
        print(f"{name}  {type(obj).__name__}")
```
</example>

<example>
User: what is a Graph in bae?
Assistant: A Graph is a directed agent graph built from Node type hints. It routes execution through nodes based on type annotations, with each node producing a typed output that determines the next node.
</example>
</examples>

## Tools
- `ns()` list all namespace objects with types.
    `ns(obj)` deep-inspect any object.
- Python interpreter: define classes, call functions, import modules.
"""


# ---------------------------------------------------------------------------
# Public dicts keyed by convention name
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS: dict[str, str] = {
    "fence_annotation": _PROMPT_FENCE_ANNOTATION,
    "wrapper_marker": _PROMPT_WRAPPER_MARKER,
    "inverse": _PROMPT_INVERSE,
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


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_response(response: str, convention: str, expected: str) -> None:
    """Validate that a model response follows the convention correctly.

    expected types:
      no_code  -- no python fences at all
      one_exec -- at least one executable block
      no_exec  -- zero executable blocks, at least one illustrative fence
      mixed    -- at least one executable AND at least one non-executable fence
    """
    regex = CONVENTION_REGEXES[convention]
    exec_blocks = regex.findall(response)
    all_python = _ALL_PYTHON_RE.findall(response)

    if expected == "no_code":
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
        # Inverse silent-failure detection (Pitfall 5): verify illustrative
        # fences actually use the :example annotation, not bare fences.
        if convention == "inverse":
            example_fences = _EXAMPLE_FENCE_RE.findall(response)
            assert len(example_fences) >= 1, (
                f"Inverse convention: expected illustrative fences with "
                f":example annotation, but found none. The model may have "
                f"written bare fences (silent compliance failure).\n"
                f"Response:\n{response}"
            )

    elif expected == "mixed":
        assert len(exec_blocks) >= 1, (
            f"Expected at least one executable block, got none.\n"
            f"Response:\n{response}"
        )
        # There should be more total python fences than executable ones
        assert len(all_python) > len(exec_blocks), (
            f"Expected illustrative blocks beyond exec blocks. "
            f"Total python fences: {len(all_python)}, exec: {len(exec_blocks)}.\n"
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
