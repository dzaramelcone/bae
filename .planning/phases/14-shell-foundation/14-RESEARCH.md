# Phase 14: Shell Foundation - Research

**Researched:** 2026-02-13
**Domain:** Async REPL shell with prompt_toolkit, mode switching, Python execution with top-level await, bash subprocess dispatch
**Confidence:** HIGH

## Summary

Phase 14 builds the cortex REPL -- an async prompt_toolkit shell with four modes (NL, Py, Graph, Bash), good Python text editing, and clean lifecycle. This is bae's first v4.0 phase; it has no dependencies on other v4.0 phases.

The core technical challenge is event loop sovereignty: cortex owns the single asyncio event loop via `asyncio.run()`, and all execution (Python code, graph runs, bash commands) happens cooperatively within that loop. prompt_toolkit 3.0's `PromptSession.prompt_async()` yields control to the event loop while waiting for input, enabling background tasks and concurrent execution.

The key research finding is that Python 3.14's `ast.PyCF_ALLOW_TOP_LEVEL_AWAIT` compile flag makes top-level await trivial -- compile user code with this flag, exec via `types.FunctionType`, and await the result if it's a coroutine. No AST rewriting, no wrapper functions, no IPython-style hacks. This was verified on the project's Python 3.14.3 runtime.

A critical terminal compatibility finding: Shift+Enter is NOT a universal terminal key. Most terminals send the same escape sequence for Enter and Shift+Enter. However, prompt_toolkit's solution for "Enter submits, newline on demand" is well-established: bind Enter to `validate_and_handle()` and bind Escape+Enter (Meta+Enter) to insert newline. The decision says "Shift+Enter inserts newline" -- this will work on terminals that support the kitty keyboard protocol (Ghostty, kitty, iTerm2 with CSI u) but falls back to Escape+Enter on others. The implementation should bind both `s-tab` (which works) for mode cycling and handle the Enter/newline split via the Meta+Enter pattern.

**Primary recommendation:** Build the shell as a single `bae/repl/` package with `shell.py` (PromptSession + mode dispatch), `modes.py` (per-mode handlers), and `exec.py` (async Python execution). Use `ast.PyCF_ALLOW_TOP_LEVEL_AWAIT` for top-level await. Use `asyncio.create_subprocess_shell()` for bash mode. Keep it minimal -- no channels, no AI, no OTel in this phase.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Prompt & mode identity
- Clean minimal prompt: `> ` style, no mode name in the prompt itself
- Mode indicated by prompt color -- each mode has a distinct color (NL, Py, Graph, Bash)
- Bottom status bar (persistent, like vim) shows: active mode name + working directory
- No keybinding hints or help text in the status bar -- users learn from docs

#### Multiline editing
- Enter submits, Shift+Enter inserts newline -- consistent across ALL modes
- Auto-indentation in Py mode: Claude's discretion (smart indent or basic, whatever prompt_toolkit does well)
- Tab completion in Py mode: Claude's discretion (pick what prompt_toolkit supports cleanly)
- Syntax highlighting in Py mode (per spec)

#### Launch
- `bae` with no arguments launches cortex -- silent start, straight to prompt, no banner
- Default mode is NL (even though NL is a stub in Phase 14)
- No CLI arguments in Phase 14 -- `bae` launches the REPL, period
- No in-REPL help/discovery mechanism

#### Bash mode execution model
- The REPL owns a cwd; bash commands execute via Python subprocess inheriting that cwd
- `cd` is special-cased: updates the REPL's working directory (os.chdir), affects all modes
- Each non-cd bash command spawns a subprocess, returns stdout/stderr
- Stderr displayed in red, stdout plain
- User navigates the OS and spawns processes through bash mode; results flow back to the REPL
- No shell state carries over between commands (env vars, aliases) -- each is a fresh subprocess

#### Mode stubs
- Graph mode: exists in the mode cycle (Shift+Tab reaches it), but input is a no-op/stub message
- NL mode: exists and is the default; Claude's discretion on stub behavior (echo, pass-to-py fallback, or stub message)

#### Shutdown & interrupt
- Ctrl-C with nothing running: single press exits immediately, no confirmation
- Ctrl-C while code is running in Py mode: raises KeyboardInterrupt (standard Python behavior), does NOT exit the REPL
- Ctrl-D: graceful shutdown -- cancels tasks, drains queues, brief summary line (`cancelled N tasks`), then exits
- Ctrl-D with nothing running: silent exit, straight back to shell
- Unhandled exceptions in Py mode: standard Python traceback (full, familiar)

### Claude's Discretion
- Auto-indentation approach in Py mode (smart vs basic -- whatever prompt_toolkit does well)
- Tab completion depth (namespace + builtins vs Jedi-style -- pick what works)
- NL mode stub behavior before Phase 18 wires up the AI agent
- Prompt colors per mode
- Status bar styling

### Deferred Ideas (OUT OF SCOPE)
- Language server (LSP) integration for completion (both user typing and AI code generation) -- future phase
- CLI arguments (`bae py`, `bae -c 'expr'`) -- future phase
- In-REPL help system -- future phase or docs
</user_constraints>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `prompt-toolkit` | >=3.0.50 | Async REPL shell: PromptSession, key bindings, lexer, completer, bottom toolbar | Native asyncio since 3.0. `prompt_async()` yields to event loop. Only dep is `wcwidth`. IPython itself is built on prompt_toolkit. |
| `pygments` | >=2.19 | Python syntax highlighting in Py mode via `PygmentsLexer(PythonLexer)` | prompt_toolkit's lexer integration expects Pygments lexers. Already transitive via typer/rich. |

### Supporting (stdlib -- no new deps)

| Library | Purpose | When to Use |
|---------|---------|-------------|
| `ast` (stdlib) | Parse user code, detect expressions, `PyCF_ALLOW_TOP_LEVEL_AWAIT` flag | Every Python execution in Py mode |
| `types` (stdlib) | `FunctionType` to execute compiled code with custom namespace | Core of async exec pattern |
| `asyncio` (stdlib) | Event loop, `create_subprocess_shell`, `Queue.shutdown()` | Event loop ownership, bash mode, shutdown |
| `rlcompleter` (stdlib) | Namespace-aware tab completion (`Completer.complete()`) | Py mode tab completion |
| `os` (stdlib) | `os.chdir()` for `cd` special-casing, `os.getcwd()` for status bar | Bash mode cwd management |
| `traceback` (stdlib) | Format Python exceptions for display | Error handling in Py mode |
| `subprocess` / `asyncio.subprocess` | Execute bash commands | Bash mode |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `rlcompleter` | `jedi` library | Jedi gives deeper static analysis (type inference, docstrings) but adds ~10MB dep and can be slow. rlcompleter is fast, already in stdlib, uses `dir()` on live objects. Start with rlcompleter, Jedi is a future LSP concern. |
| Custom async exec | `ptpython.repl.embed()` | ptpython gives a full REPL for free but takes over the prompt session. We need mode switching and custom key bindings that ptpython doesn't support. Build our own thin exec layer. |
| `asyncio.create_subprocess_shell` | `subprocess.run` in thread | `create_subprocess_shell` is native async, no thread pool needed. `subprocess.run` would block the event loop. |

**Installation:**
```bash
pip install "prompt-toolkit>=3.0.50" "pygments>=2.19"
```

## Architecture Patterns

### Recommended Project Structure

```
bae/repl/
    __init__.py     # launch() entry point
    shell.py        # CortexShell: PromptSession + mode dispatch + lifecycle
    modes.py        # Mode enum, per-mode config (color, lexer, completer)
    exec.py         # async_exec(): PyCF_ALLOW_TOP_LEVEL_AWAIT execution engine
    bash.py         # run_bash(): subprocess dispatch, cd special-casing
```

### Pattern 1: Async Python Execution with Top-Level Await

**What:** Execute user Python code that may contain `await` expressions, capturing the last expression result in `_`.

**When to use:** Every Py mode input submission.

**Verified on Python 3.14.3:**

```python
import ast
import asyncio
import types

async def async_exec(code_str: str, namespace: dict) -> object | None:
    """Execute code with top-level await support."""
    tree = ast.parse(code_str, mode="exec")

    # If last statement is an expression, rewrite to assign to _
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_expr = tree.body[-1]
        assign = ast.Assign(
            targets=[ast.Name(id="_", ctx=ast.Store())],
            value=last_expr.value,
        )
        tree.body[-1] = assign
        ast.fix_missing_locations(tree)

    compiled = compile(
        tree, "<cortex>", "exec",
        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
    )
    fn = types.FunctionType(compiled, namespace)
    result = fn()
    if asyncio.iscoroutine(result):
        await result

    return namespace.get("_")
```

**Confidence:** HIGH -- verified working on Python 3.14.3 with sync code, await expressions, multiline code, and expression capture.

### Pattern 2: Mode-Switched PromptSession with Colored Prompts

**What:** Single `PromptSession` that changes prompt color, lexer, and completer based on active mode.

**When to use:** The core REPL loop.

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.lexers import PygmentsLexer, DynamicLexer
from prompt_toolkit.completion import DynamicCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from pygments.lexers.python import PythonLexer

# Mode state
current_mode = "nl"  # nl, py, graph, bash

# Mode colors (prompt_toolkit style tuples)
MODE_COLORS = {
    "nl":    "#87d7ff",  # light blue
    "py":    "#87ff87",  # light green
    "graph": "#ffaf87",  # light orange
    "bash":  "#d7afff",  # light purple
}

def get_prompt():
    """Dynamic prompt -- color changes with mode."""
    color = MODE_COLORS[current_mode]
    return [("", "> ")]  # clean minimal prompt, colored via style

def get_lexer():
    """Return lexer for current mode."""
    if current_mode == "py":
        return PygmentsLexer(PythonLexer)
    return None  # no highlighting for other modes

def get_completer():
    """Return completer for current mode."""
    if current_mode == "py":
        return py_completer  # rlcompleter-based
    return None

# Key bindings for mode cycling
kb = KeyBindings()

@kb.add("s-tab")  # Shift+Tab -- works in all terminals
def cycle_mode(event):
    global current_mode
    modes = ["nl", "py", "graph", "bash"]
    idx = modes.index(current_mode)
    current_mode = modes[(idx + 1) % len(modes)]
    # Force toolbar refresh
    event.app.invalidate()

session = PromptSession(
    message=get_prompt,
    lexer=DynamicLexer(get_lexer),
    completer=DynamicCompleter(get_completer),
    key_bindings=kb,
    bottom_toolbar=get_toolbar,  # see Pattern 5
    style=get_style(),
)
```

**Confidence:** HIGH -- prompt_toolkit docs confirm `DynamicLexer`, `DynamicCompleter`, `s-tab` key name, and callable prompt all work.

### Pattern 3: Enter Submits, Escape+Enter Inserts Newline

**What:** Reverse prompt_toolkit's default multiline behavior so Enter submits and a modifier key inserts newline.

**Critical finding:** Shift+Enter is NOT universally recognized by terminals. Most terminals send the same escape sequence for Enter and Shift+Enter. Terminals with kitty keyboard protocol support (Ghostty, kitty, iTerm2 with CSI u mode) do distinguish them. The safe approach: bind Enter to submit, bind `escape` `enter` (Meta+Enter) to insert newline. This works everywhere.

```python
@kb.add("enter")
def submit(event):
    """Enter submits input."""
    event.current_buffer.validate_and_handle()

@kb.add("escape", "enter")
def newline(event):
    """Meta+Enter (Escape then Enter) inserts newline."""
    event.current_buffer.insert_text("\n")
```

**Important:** This requires `multiline=True` on the PromptSession so the buffer can hold multiple lines. With `multiline=True`, the default behavior is reversed (Enter = newline, Meta+Enter = submit). Our custom bindings override both to get the desired behavior.

**Terminal compatibility note:** On terminals that DO support Shift+Enter as a distinct key (kitty protocol), prompt_toolkit currently does NOT have a built-in `s-enter` key name. Shift+Enter would need terminal-specific escape sequence registration. The Escape+Enter pattern is the universally reliable approach.

**Confidence:** HIGH -- verified via prompt_toolkit issue #728 solution and official key bindings docs.

### Pattern 4: Bash Subprocess Execution

**What:** Run bash commands via `asyncio.create_subprocess_shell`, special-case `cd`.

```python
import asyncio
import os
import shlex

async def run_bash(cmd: str, cwd: str) -> tuple[str, str, int]:
    """Execute a bash command, return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(), stderr.decode(), proc.returncode

def handle_cd(args: str) -> str | None:
    """Handle cd command. Returns error message or None on success."""
    target = args.strip() or os.path.expanduser("~")
    target = os.path.expanduser(target)
    try:
        os.chdir(target)
        return None
    except FileNotFoundError:
        return f"cd: no such file or directory: {target}"
    except PermissionError:
        return f"cd: permission denied: {target}"

def is_cd_command(cmd: str) -> tuple[bool, str]:
    """Check if command is a cd. Returns (is_cd, args)."""
    stripped = cmd.strip()
    if stripped == "cd" or stripped.startswith("cd "):
        return True, stripped[2:].strip()
    return False, ""
```

**Confidence:** HIGH -- verified `asyncio.create_subprocess_shell` with cwd parameter and `os.chdir` on Python 3.14.3.

### Pattern 5: Persistent Bottom Status Bar

**What:** A vim-style bottom toolbar showing active mode name and working directory.

```python
from prompt_toolkit.formatted_text import HTML

def get_toolbar():
    """Bottom toolbar: mode name + cwd. Re-evaluated each render."""
    mode_name = current_mode.upper()
    cwd = os.getcwd()
    # Shorten home directory
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]
    return HTML(f"<b>{mode_name}</b>  {cwd}")
```

**Note:** The toolbar is re-rendered on every UI invalidation. Calling `event.app.invalidate()` after mode switches forces an immediate toolbar update. The callable pattern ensures the cwd is always current.

**Confidence:** HIGH -- verified via prompt_toolkit bottom-toolbar examples and official docs.

### Pattern 6: Graceful Shutdown Sequence

**What:** Ordered shutdown on Ctrl-D with task cancellation and summary.

```python
async def shutdown(tasks: set[asyncio.Task]) -> None:
    """Cancel all tasks, drain, report summary."""
    if not tasks:
        return  # silent exit

    # Cancel all running tasks
    for task in tasks:
        task.cancel()

    # Wait for cancellation with timeout
    results = await asyncio.gather(*tasks, return_exceptions=True)

    cancelled = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
    if cancelled:
        print(f"cancelled {cancelled} tasks")
```

**Confidence:** HIGH -- verified `asyncio.Task.cancel()` and gather with `return_exceptions=True` on Python 3.14.3.

### Anti-Patterns to Avoid

- **Nested `asyncio.run()`:** Never call `graph.run()` from within the REPL. Always use `await graph.arun()`. The sync wrapper calls `asyncio.run()` which fails inside a running loop.
- **`nest_asyncio`:** Do not use this library. It papers over the nested loop problem but introduces reentrancy hazards with bae's `asyncio.gather()` calls.
- **Raw `print()` inside the REPL loop:** Use `print_formatted_text()` from prompt_toolkit when inside `patch_stdout()` context. Raw print is fine for simple cases but may cause issues with concurrent output in future phases.
- **Thread-based REPL:** Do not run prompt_toolkit in a separate thread. Single asyncio loop, single thread. prompt_toolkit 3.0 supports this natively.
- **`get_event_loop()`:** Use `asyncio.get_running_loop()` (Python 3.10+). `get_event_loop()` is deprecated for contexts where a loop may not be running.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Syntax highlighting | Custom token parser | `PygmentsLexer(PythonLexer)` | Pygments has complete Python lexer with all edge cases (f-strings, match statements, type params). One line of code. |
| Tab completion for namespace | Walk `dir()` manually | `rlcompleter.Completer(namespace)` | stdlib, handles dot-attribute chains (`obj.attr.sub`), callable signatures, keyword completion. Wrap in prompt_toolkit `Completer` interface. |
| Multiline editing | Custom line buffer | prompt_toolkit `multiline=True` + custom key bindings | prompt_toolkit handles cursor movement, history navigation, paste detection, soft-wrap. |
| Terminal color management | ANSI escape codes | prompt_toolkit `Style.from_dict()` + style classes | prompt_toolkit manages terminal state, resets colors properly, handles non-color terminals. |
| Key binding system | Custom input parser | prompt_toolkit `KeyBindings` | Handles escape sequences, modifier keys, terminal differences. |

**Key insight:** prompt_toolkit handles the terminal interaction layer entirely. The REPL code should focus on mode dispatch, Python execution, and bash subprocess management -- NOT terminal rendering.

## Common Pitfalls

### Pitfall 1: Event Loop Conflict with graph.run()

**What goes wrong:** Calling `graph.run()` from the REPL triggers `asyncio.run()` inside an already-running event loop, causing `RuntimeError`.

**Why it happens:** `Graph.run()` (line 217 of graph.py) wraps `Graph.arun()` with `asyncio.run()`. This works for scripts but not inside cortex's event loop.

**How to avoid:** Always use `await graph.arun()` in the REPL. In Phase 14, Py mode executes code with `PyCF_ALLOW_TOP_LEVEL_AWAIT`, so `await` works naturally. Consider adding a clear error message to `graph.run()` when it detects a running loop:
```python
def run(self, ...):
    try:
        asyncio.get_running_loop()
        raise RuntimeError(
            "graph.run() cannot be used inside cortex. "
            "Use 'await graph.arun(...)' instead."
        )
    except RuntimeError:
        pass  # No running loop, safe to proceed
    return asyncio.run(self.arun(...))
```

**Warning signs:** `RuntimeError: asyncio.run() cannot be called from a running event loop`

### Pitfall 2: Shift+Enter Terminal Incompatibility

**What goes wrong:** The decision specifies "Shift+Enter inserts newline" but most terminals don't distinguish Shift+Enter from plain Enter.

**Why it happens:** Traditional VT100 terminal protocol sends `\r` (CR) for both Enter and Shift+Enter. Only terminals implementing the kitty keyboard protocol (Ghostty, kitty, iTerm2 with CSI u mode) send a distinct escape sequence for Shift+Enter.

**How to avoid:** Implement Enter-submits and Escape+Enter-for-newline as the base behavior. This works in ALL terminals. For terminals that support distinct Shift+Enter sequences, additionally register that sequence as a newline binding. The user experience is:
- Ghostty/kitty users: Shift+Enter works as expected
- Other terminals: Escape then Enter (or Alt+Enter) inserts newline
- Enter always submits

**Warning signs:** Shift+Enter submits instead of inserting newline on some terminals.

### Pitfall 3: Bottom Toolbar Disappears Between Prompts

**What goes wrong:** prompt_toolkit's documentation states "The toolbar is always erased when the prompt returns." This means the status bar disappears after each command, unlike vim's persistent status line.

**How to avoid:** The toolbar reappears when the next `prompt_async()` call starts. In practice, the gap between command execution and the next prompt is brief. For the "persistent" feel:
1. Use `patch_stdout()` context wrapping the entire REPL session
2. The toolbar callable is re-evaluated each time the prompt renders
3. During command execution, the toolbar is gone (this is acceptable -- vim also refreshes its status line)

If truly persistent display is needed, the full-screen `Application` API with `HSplit`/`VSplit` layout would be required, but that's overengineering for Phase 14.

### Pitfall 4: User Code Exceptions Crash the REPL

**What goes wrong:** An unhandled exception from `exec()` propagates past the REPL loop, crashing cortex.

**Why it happens:** Bae's convention is "let errors propagate" (CONVENTIONS.md). This is correct for library code but the REPL is the outermost exception boundary.

**How to avoid:** Catch `Exception` (not `BaseException`) around the exec call. Print full traceback. Let `KeyboardInterrupt` and `SystemExit` propagate.

```python
try:
    result = await async_exec(code, namespace)
    if result is not None:
        print(repr(result))
except KeyboardInterrupt:
    pass  # Ctrl-C during execution -- swallow, return to prompt
except Exception:
    traceback.print_exc()
```

### Pitfall 5: namespace dict vs FunctionType globals

**What goes wrong:** When using `types.FunctionType(compiled, namespace)`, the `namespace` dict IS the function's `__globals__`. This means the executed code can see and modify everything in `namespace`. But variables assigned inside the code are added to `namespace` directly (since it's the globals dict). This is the desired behavior for a REPL but surprising if you expect isolation.

**Why it matters:** Every mode shares the same namespace dict. A variable set in Py mode is visible in NL mode's stub. An `import` in Py mode adds to the shared namespace. This is correct per the architecture but must be deliberate.

**How to avoid:** Document that the namespace is shared. Use a single dict throughout. Do not create per-mode namespaces.

### Pitfall 6: Ctrl-C Behavior Depends on Context

**What goes wrong:** The decision specifies three different Ctrl-C behaviors:
1. Nothing running + Ctrl-C: exit immediately
2. Code running in Py mode + Ctrl-C: raise KeyboardInterrupt in the code, stay in REPL
3. (Future: Phase 19) Tasks running + Ctrl-C: open task kill menu

**Why it's tricky:** prompt_toolkit's `prompt_async()` raises `KeyboardInterrupt` when Ctrl-C is pressed during input. But when code is executing (between prompts), Ctrl-C sends SIGINT which asyncio translates to `CancelledError` on the current task.

**How to avoid:** Use prompt_toolkit's built-in behavior:
- During `prompt_async()`: catch `KeyboardInterrupt`, check if tasks running. If no tasks, exit. If tasks (future), show menu.
- During code execution: the `KeyboardInterrupt` propagates into the running code naturally. Catch it at the REPL loop level and return to prompt.

## Code Examples

### Complete REPL Loop (Minimal)

```python
# Source: Synthesis of official prompt_toolkit asyncio-prompt.py example
# + PyCF_ALLOW_TOP_LEVEL_AWAIT pattern verified on Python 3.14.3

import asyncio
import ast
import os
import traceback
import types

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import DynamicLexer, PygmentsLexer
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from pygments.lexers.python import PythonLexer


MODES = ["nl", "py", "graph", "bash"]
MODE_COLORS = {
    "nl": "#87d7ff",
    "py": "#87ff87",
    "graph": "#ffaf87",
    "bash": "#d7afff",
}

current_mode = "nl"
namespace = {"asyncio": asyncio, "os": os}


def get_prompt():
    color = MODE_COLORS[current_mode]
    return [("fg:" + color, "> ")]


def get_toolbar():
    mode = current_mode.upper()
    cwd = os.getcwd()
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]
    return [("class:toolbar.mode", f" {mode} "), ("class:toolbar.cwd", f" {cwd} ")]


def get_lexer():
    if current_mode == "py":
        return PygmentsLexer(PythonLexer)
    return None


kb = KeyBindings()


@kb.add("s-tab")
def cycle_mode(event):
    global current_mode
    idx = MODES.index(current_mode)
    current_mode = MODES[(idx + 1) % len(MODES)]
    event.app.invalidate()


@kb.add("enter")
def submit(event):
    event.current_buffer.validate_and_handle()


@kb.add("escape", "enter")
def insert_newline(event):
    event.current_buffer.insert_text("\n")


style = Style.from_dict({
    "": MODE_COLORS["nl"],  # default prompt color
    "toolbar": "bg:#333333 #ffffff",
    "toolbar.mode": "bg:#555555 #ffffff bold",
    "toolbar.cwd": "bg:#333333 #aaaaaa",
    "bottom-toolbar": "bg:#333333",
})


async def async_exec(code_str, ns):
    tree = ast.parse(code_str, mode="exec")
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_expr = tree.body[-1]
        assign = ast.Assign(
            targets=[ast.Name(id="_", ctx=ast.Store())],
            value=last_expr.value,
        )
        tree.body[-1] = assign
        ast.fix_missing_locations(tree)

    compiled = compile(
        tree, "<cortex>", "exec",
        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
    )
    fn = types.FunctionType(compiled, ns)
    coro = fn()
    if asyncio.iscoroutine(coro):
        await coro


async def main():
    global current_mode

    session = PromptSession(
        message=get_prompt,
        lexer=DynamicLexer(get_lexer),
        key_bindings=kb,
        bottom_toolbar=get_toolbar,
        style=style,
        multiline=True,
    )

    with patch_stdout():
        while True:
            try:
                text = await session.prompt_async()
                if not text.strip():
                    continue

                if current_mode == "py":
                    try:
                        await async_exec(text, namespace)
                        result = namespace.get("_")
                        if result is not None:
                            print(repr(result))
                    except KeyboardInterrupt:
                        pass
                    except Exception:
                        traceback.print_exc()

                elif current_mode == "bash":
                    # ... bash dispatch
                    pass

                elif current_mode in ("nl", "graph"):
                    print(f"[{current_mode}] mode stub -- not yet implemented")

            except KeyboardInterrupt:
                return  # exit on Ctrl-C at prompt
            except EOFError:
                return  # exit on Ctrl-D


if __name__ == "__main__":
    asyncio.run(main())
```

### Tab Completion for Py Mode (rlcompleter wrapper)

```python
# Source: Python stdlib rlcompleter + prompt_toolkit Completer interface

import rlcompleter
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


class NamespaceCompleter(Completer):
    """Tab completer using rlcompleter on the REPL namespace."""

    def __init__(self, namespace: dict):
        self._namespace = namespace
        self._completer = rlcompleter.Completer(namespace)

    def get_completions(self, document: Document, complete_event):
        # Get the text to complete (word before cursor)
        text = document.get_word_before_cursor(WORD=True)

        # Use rlcompleter to find matches
        completions = []
        i = 0
        while True:
            match = self._completer.complete(text, i)
            if match is None:
                break
            completions.append(match)
            i += 1

        # Yield prompt_toolkit Completion objects
        for c in completions:
            # start_position is negative offset from cursor
            yield Completion(c, start_position=-len(text))
```

**Confidence:** HIGH -- `rlcompleter.Completer` verified on Python 3.14.3. Handles global names, dot-attribute chains, and callable signatures.

### Bash Mode with cd Special-Casing

```python
# Source: Verified on Python 3.14.3 asyncio.create_subprocess_shell

import asyncio
import os
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit import print_formatted_text


async def dispatch_bash(cmd: str) -> None:
    """Execute a bash command or handle cd."""
    stripped = cmd.strip()
    if not stripped:
        return

    # cd special-case
    if stripped == "cd" or stripped.startswith("cd "):
        target = stripped[2:].strip() or os.path.expanduser("~")
        target = os.path.expanduser(target)
        try:
            os.chdir(target)
        except (FileNotFoundError, PermissionError) as e:
            print_formatted_text(FormattedText([("fg:red", str(e))]))
        return

    # All other commands: subprocess
    proc = await asyncio.create_subprocess_shell(
        stripped,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd(),
    )
    stdout, stderr = await proc.communicate()

    if stdout:
        print(stdout.decode(), end="")
    if stderr:
        print_formatted_text(
            FormattedText([("fg:red", stderr.decode())])
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.run()` inside REPL | `prompt_async()` on shared loop | prompt_toolkit 3.0 (2019) | No nested event loops needed |
| AST rewriting for top-level await | `ast.PyCF_ALLOW_TOP_LEVEL_AWAIT` compile flag | Python 3.8 (2019, bpo-34616) | Single compile() call, no AST manipulation |
| `asyncio.get_event_loop()` | `asyncio.get_running_loop()` | Python 3.10 (deprecated old) | Correct loop access inside async code |
| aiochannel for closable queues | `asyncio.Queue.shutdown()` | Python 3.13 (stdlib) | No external dep for queue lifecycle |
| readline-based completion | prompt_toolkit `Completer` + `rlcompleter` | prompt_toolkit 3.0 | Rich UI, popup menus, styled completions |

## Discretion Recommendations

### Auto-indentation in Py mode

**Recommendation:** Use prompt_toolkit's built-in auto-indent behavior. When `multiline=True` is set, prompt_toolkit handles basic auto-indentation (continuing the previous line's indent level). For smarter indentation (indent after `:`, dedent after `return`), this would require a custom `Validator` or key binding that inspects the current line. Start with basic (what prompt_toolkit gives for free), enhance later if needed.

**Confidence:** MEDIUM -- prompt_toolkit's built-in auto-indent behavior is not extensively documented. May need to be tested empirically.

### Tab completion depth

**Recommendation:** Use `rlcompleter.Completer` wrapping the REPL namespace. This gives:
- Global name completion (`asyncio`, `os`, user variables)
- Dot-attribute completion (`asyncio.sleep`, `result.trace`)
- Multi-level dot chains (`result.trace[0].model_dump`)
- Callable signature hints (appends `(` for callables)
- Keyword completion (`for`, `while`, `import`)

This is the same approach CPython's own REPL uses. Wrap in `ThreadedCompleter` if any completion operation is slow. No Jedi needed for Phase 14.

### NL mode stub behavior

**Recommendation:** Echo the input back with a "NL mode not yet available" message. Do not pass to Py mode (confusing -- user expects NL behavior, gets Python syntax errors). Keep it honest:

```python
if current_mode == "nl":
    print(f"(NL mode stub) You said: {text}")
    print("NL mode will be available in Phase 18 (AI Agent).")
```

### Prompt colors per mode

**Recommendation:** Use ANSI-safe colors that work on both light and dark terminals:

| Mode | Prompt Color | Rationale |
|------|-------------|-----------|
| NL | `#87d7ff` (light blue) | Blue for conversation/AI, calm |
| Py | `#87ff87` (light green) | Green for code, like terminal green |
| Graph | `#ffaf87` (light orange) | Orange for graph/structure, warm |
| Bash | `#d7afff` (light purple) | Purple for system/shell, distinct |

These are 256-color palette values that render correctly on most terminals.

### Status bar styling

**Recommendation:** Dark background, mode name bold, cwd in muted text:

```python
Style.from_dict({
    "bottom-toolbar": "bg:#1c1c1c #808080",
    "bottom-toolbar.mode": "bg:#303030 #ffffff bold",
    "bottom-toolbar.cwd": "#808080",
})
```

## Open Questions

1. **Prompt color changes with mode**
   - What we know: prompt_toolkit supports callable message that returns style tuples. The style can include per-character colors.
   - What's unclear: Whether changing the *default text style* (not just prompt prefix) per mode is needed. The decision says "mode indicated by prompt color" which could mean just the `> ` characters are colored, or the entire input text color changes.
   - Recommendation: Color only the `> ` prompt prefix. Input text uses terminal default. Simpler and less visually noisy.

2. **Completion provider interface for future LSP**
   - What we know: The deferred ideas mention "clean provider interface" for future LSP integration.
   - What's unclear: Whether Phase 14's completer should already have an abstract interface or just be rlcompleter directly.
   - Recommendation: Use a concrete `NamespaceCompleter(Completer)` class (not just a bare function). This class can be swapped for an LSP-backed completer later. The `Completer` ABC from prompt_toolkit IS the provider interface.

3. **`bae` entry point change**
   - What we know: Currently `bae` runs `no_args_is_help=True` typer app. REPL-01 says `bae` with no args launches cortex.
   - What's unclear: Whether existing `bae graph show` etc. commands should still work alongside the no-args REPL launch.
   - Recommendation: Change `no_args_is_help=True` to `invoke_without_command=True` with a default callback that launches cortex. Subcommands (`bae graph show`, `bae run`) continue working as before.

## Sources

### Primary (HIGH confidence)

- [prompt_toolkit asking for input docs (3.0.52)](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html) -- PromptSession, multiline, lexer, completer, bottom_toolbar, styled prompt
- [prompt_toolkit key bindings docs (3.0.52)](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/key_bindings.html) -- `s-tab` key name confirmed, KeyBindings API
- [prompt_toolkit asyncio-prompt.py example](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/prompts/asyncio-prompt.py) -- canonical async REPL pattern with patch_stdout
- [prompt_toolkit bottom-toolbar.py example](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/prompts/bottom-toolbar.py) -- toolbar callable, HTML, style tuples, dynamic refresh
- [prompt_toolkit keys.py source](https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/src/prompt_toolkit/keys.py) -- `BackTab = "s-tab"` confirmed, no `ShiftEnter` key
- [Python 3.14 ast module docs](https://docs.python.org/3/library/ast.html) -- `PyCF_ALLOW_TOP_LEVEL_AWAIT` flag
- [Python 3.14 asyncio.Queue docs](https://docs.python.org/3/library/asyncio-queue.html) -- `Queue.shutdown()`, `QueueShutDown`
- [Python rlcompleter docs](https://docs.python.org/3/library/rlcompleter.html) -- namespace-aware completion
- [ptpython asyncio-python-embed.py](https://github.com/prompt-toolkit/ptpython/blob/main/examples/asyncio-python-embed.py) -- async REPL embedding pattern
- prompt_toolkit issue #728 -- [Enter submits, Meta+Enter newline solution](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/728)
- prompt_toolkit issue #529 -- [Shift+Enter terminal limitations](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/529)
- Runtime verification on Python 3.14.3: `PyCF_ALLOW_TOP_LEVEL_AWAIT`, `asyncio.Queue.shutdown()`, `types.FunctionType` async exec pattern

### Secondary (MEDIUM confidence)

- [kitty keyboard protocol](https://sw.kovidgoyal.net/kitty/keyboard-protocol/) -- CSI u encoding for Shift+Enter
- [Ghostty Shift+Enter discussion #7780](https://github.com/ghostty-org/ghostty/discussions/7780) -- terminal-specific escape sequences
- [IPython autoawait docs](https://ipython.readthedocs.io/en/stable/interactive/autoawait.html) -- historical context for top-level await in REPLs
- [Carreau: Writing an async REPL](https://carreau.github.io/posts/27-Writing-an-async-REPL---Part-1.ipynb/) -- AST approach (superseded by PyCF_ALLOW_TOP_LEVEL_AWAIT)
- [prompt_toolkit issue #751](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/751) -- bottom toolbar refresh via callable
- [prompt_toolkit issue #1079](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1079) -- patch_stdout missing prints on exit

### Prior Research (this project)

- `.planning/research/STACK.md` -- prompt_toolkit selection, asyncio.Queue.shutdown(), pygments
- `.planning/research/ARCHITECTURE.md` -- CortexShell design, event loop sovereignty, module structure
- `.planning/research/PITFALLS.md` -- event loop conflict, output corruption, shutdown sequence, namespace isolation
- `.planning/research/FEATURES.md` -- mode switching patterns, channel I/O, tab completion approaches

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- prompt_toolkit and pygments are the only additions; both verified
- Architecture: HIGH -- async exec pattern verified on Python 3.14.3, prompt_toolkit APIs confirmed in docs
- Pitfalls: HIGH -- terminal key compatibility researched, event loop conflict well-documented
- Discretion items: MEDIUM -- color choices and auto-indent behavior need empirical testing

**Research date:** 2026-02-13
**Valid until:** 2026-03-15 (stable libraries, unlikely to change)
