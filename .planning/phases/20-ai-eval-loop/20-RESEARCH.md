# Phase 20: AI Eval Loop - Research

**Researched:** 2026-02-14
**Domain:** AI agent eval loop, markdown terminal rendering, multi-session management, cross-session memory
**Confidence:** HIGH

## Summary

Phase 20 has seven success criteria spanning five distinct technical domains: (1) AI code extraction and execution feedback loop, (2) multi-session AI management with NL mode selector, (3) cross-session memory from the store, (4) markdown rendering in the terminal, and (5) task menu UX change from toolbar to scrollback.

The codebase already has all the building blocks. `AI.extract_code()` parses Python code blocks. `async_exec()` executes code in the shared namespace. `ChannelRouter.write()` displays output. `SessionStore` persists all I/O with FTS5 search. `TaskManager` tracks background tasks. The work is connecting these pieces into an eval loop and adding two new capabilities: Rich-based markdown rendering and multi-session AI routing.

**Primary recommendation:** Use Rich (already Python 3.14 compatible) for markdown-to-ANSI conversion, piped through prompt_toolkit's `ANSI` class for display. The eval loop is a simple while loop: extract code from AI response, execute it, feed stdout/stderr back as the next prompt. Multi-session routing uses a dict of AI instances keyed by session label.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| rich | >=14.3 | Markdown-to-ANSI terminal rendering | 150M+ downloads/month, Python 3.14 support, `Markdown` class handles headers/bold/code/lists out of the box |
| prompt-toolkit | >=3.0.50 | Already in use. `ANSI` class parses Rich output for display | Already a dependency; `print_formatted_text(ANSI(...))` works inside `patch_stdout` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | | | All other needs are met by existing dependencies |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Rich Markdown | Manual ANSI formatting | Rich handles edge cases (nested formatting, code block syntax highlighting, list indentation) that hand-rolled regex would miss. No reason to hand-roll. |
| Rich Markdown | mdcat / glow (external) | External binary dependency. Rich is pure Python, already in the ecosystem (typer uses it internally). |

**Installation:**
```bash
uv add "rich>=14.3"
```

## Architecture Patterns

### Existing File Structure (no new files needed for eval loop core)
```
bae/repl/
    ai.py           # AI class -- add eval loop, multi-session, cross-session context
    channels.py     # Channel._display -- add markdown rendering path
    shell.py        # CortexShell -- add session selector, task menu scrollback
    store.py        # SessionStore -- add cross-session context query
    toolbar.py      # render_task_menu -- move to scrollback printing
    ai_prompt.md    # System prompt -- update for eval loop behavior
```

### Pattern 1: AI Eval Loop (extract-execute-feedback)
**What:** After AI responds, extract Python code blocks, execute each in the REPL namespace, capture output, feed results back as the next AI prompt. Loop until AI responds with no code blocks or a configurable iteration limit.
**When to use:** Every AI `__call__` invocation.
**Key design:** The loop runs INSIDE `AI.__call__`, not in the shell. This keeps the eval loop self-contained and testable.

```python
# Simplified eval loop structure (inside AI.__call__)
async def __call__(self, prompt: str) -> str:
    response = await self._send(prompt)
    self._router.write("ai", response, ...)

    iterations = 0
    while iterations < self._max_eval_iters:
        blocks = self.extract_code(response)
        if not blocks:
            break

        # Execute each code block in the REPL namespace
        results = []
        for code in blocks:
            result, captured = await async_exec(code, self._namespace)
            output = captured
            if result is not None:
                output += repr(result)
            results.append(output or "(no output)")
            self._router.write("py", ..., metadata={"type": "ai_exec"})

        # Feed results back to AI
        feedback = "\n".join(f"[Block {i+1} output]\n{r}" for i, r in enumerate(results))
        response = await self._send(feedback)
        self._router.write("ai", response, ...)
        iterations += 1

    return response
```

**Important constraints:**
- `async_exec` may return a coroutine for `await` expressions. The eval loop must await those inline (not fire-and-forget via TaskManager) because the AI needs the result.
- Iteration limit prevents infinite loops (AI generating code that generates code that...). Default 5 is reasonable.
- Each code block execution is recorded to the store via `router.write()` for auditability.
- Cancellation: `await asyncio.sleep(0)` checkpoint between iterations.

### Pattern 2: Multi-Session AI Management
**What:** Multiple AI instances keyed by label (e.g., `"1"`, `"2"`, ...) stored in a dict on the shell. NL mode routes input to the active session. PY mode `await ai("question")` creates/uses sessions that are attachable from NL mode.
**When to use:** When concurrent AI conversations need to be distinguished.

```python
# On CortexShell
class CortexShell:
    def __init__(self):
        ...
        self._ai_sessions: dict[str, AI] = {}
        self._active_session: str = "1"
        self.ai = self._get_or_create_session("1")
        self.namespace["ai"] = self.ai

    def _get_or_create_session(self, label: str) -> AI:
        if label not in self._ai_sessions:
            self._ai_sessions[label] = AI(lm=..., router=..., namespace=..., tm=..., label=label)
        return self._ai_sessions[label]
```

**Session indicator on output:** AI channel output prefixed with session label when multiple sessions exist. E.g., `[ai:1]` vs `[ai:2]`. When only one session, just `[ai]`.

**Session selector in NL mode:** A keybinding or prefix syntax to switch sessions. Options:
- Prefix: `@2 follow up on that` routes to session 2
- Keybinding: Ctrl+N cycles AI sessions (similar to Shift+Tab for modes)
- Both: prefix for explicit, keybinding for cycling

### Pattern 3: Cross-Session Memory via Store
**What:** On launch, query `SessionStore` for recent entries from previous sessions and inject a summary into the AI system prompt or first context.
**When to use:** At AI initialization, before the first `__call__`.

```python
# In AI.__init__ or a setup method
def _load_cross_session_context(self, store: SessionStore) -> str:
    """Build a summary of recent sessions for AI context."""
    recent = store.recent(n=50)  # last 50 entries across all sessions
    if not recent:
        return ""
    # Filter to interesting entries (not debug, not truncated)
    entries = [e for e in recent if e["channel"] != "debug"]
    lines = []
    for e in entries[:20]:  # cap at 20 entries
        lines.append(f"[{e['mode']}:{e['channel']}] {e['content'][:200]}")
    return "[Previous session context]\n" + "\n".join(lines)
```

**Key constraint:** This context is prepended to the FIRST prompt only (call_count == 0). Subsequent calls use `--resume` which already has conversation history.

### Pattern 4: Rich Markdown Rendering via ANSI Bridge
**What:** AI responses rendered through Rich's `Markdown` class, captured as ANSI escape sequences, then displayed via prompt_toolkit's `ANSI` class and `print_formatted_text`.
**When to use:** All `[ai]` channel output.

```python
# In channels.py or a new render helper
from io import StringIO
from rich.console import Console
from rich.markdown import Markdown

def render_markdown(text: str, width: int = 80) -> str:
    """Render markdown text to ANSI-escaped string."""
    buf = StringIO()
    console = Console(file=buf, width=width, force_terminal=True)
    console.print(Markdown(text))
    return buf.getvalue()
```

```python
# In Channel._display, for [ai] channel
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI

def _display(self, content: str) -> None:
    if self._markdown:
        ansi_text = render_markdown(content)
        # Print channel label, then rendered content
        print_formatted_text(FormattedText([(f"{self.color} bold", self.label)]))
        print_formatted_text(ANSI(ansi_text))
    else:
        # Existing line-by-line display
        for line in content.splitlines():
            ...
```

**Critical detail:** `Console(force_terminal=True)` is required because when writing to a StringIO, Rich detects it's not a terminal and strips ANSI codes. `force_terminal=True` overrides this.

### Pattern 5: Task Menu in Scrollback (not toolbar)
**What:** Replace toolbar-based task menu with printed output above the prompt. On Ctrl-C, print the numbered task list to scrollback (using `print_formatted_text`), then wait for digit/Ctrl-C/Esc input.
**When to use:** Success criterion 7 -- task menu UX.

```python
# In shell.py key binding for Ctrl-C
def handle_interrupt(event):
    if not shell.tm.active():
        event.app.exit(exception=KeyboardInterrupt())
        return
    # Print task list to scrollback instead of showing in toolbar
    active = shell.tm.active()
    for i, tt in enumerate(active, 1):
        print_formatted_text(FormattedText([
            ("bold fg:ansiyellow", f"  {i}"),
            ("", f"  {tt.name}"),
        ]))
    print_formatted_text(FormattedText([
        ("fg:#808080", "  #=cancel  ^C=all  esc=back"),
    ]))
    shell._task_menu = True  # still need state for keybinding filter
```

**Key difference from current:** Output goes to scrollback (permanent, scrollable) instead of toolbar (ephemeral, single line). The `_task_menu` flag still controls which keybindings are active, but the visual display is printed text, not toolbar content.

### Anti-Patterns to Avoid
- **Running eval loop in shell._dispatch:** The eval loop belongs in `AI.__call__`, not in the shell's dispatch. The shell just calls `await self.ai(text)` and the AI handles its own iteration.
- **Blocking on coroutine results in eval loop:** When `async_exec` returns a coroutine, the eval loop must `await` it inline to get the result for AI feedback. Do NOT fire-and-forget via TaskManager -- the AI needs the output.
- **Rich Console as global singleton:** Create a new `Console(file=StringIO(), ...)` per render call. Rich Console objects carry state (cursor position, line wrapping). Sharing one across async renders would cause state corruption.
- **Rendering markdown line-by-line:** The current `Channel._display` splits on `\n` and prints each line with a prefix. Markdown rendering MUST process the entire response as one block (headers, code blocks, lists span multiple lines). The channel label goes on a separate line before the rendered content.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Markdown rendering | Custom regex-based bold/header/list parser | Rich `Markdown` class | Handles nested formatting, code block syntax highlighting, table rendering, link formatting. Hundreds of edge cases. |
| ANSI escape code generation | Manual `\x1b[1m` strings | Rich `Console` -> `prompt_toolkit.ANSI` bridge | Cross-platform, handles 256-color, truecolor, width detection. |
| Code block extraction | New regex | Existing `AI.extract_code()` | Already tested, handles `python`/`py`/bare fences. |
| Code execution in namespace | New exec wrapper | Existing `async_exec()` | Already handles top-level await, stdout capture, expression result capture. |

**Key insight:** Every component of the eval loop already exists as a tested unit. The work is wiring them together with a feedback loop and adding Rich as a rendering layer.

## Common Pitfalls

### Pitfall 1: Rich strips ANSI when writing to StringIO
**What goes wrong:** `Console(file=StringIO())` detects non-terminal output and produces plain text without colors/formatting.
**Why it happens:** Rich's auto-detection checks `file.isatty()`, which returns False for StringIO.
**How to avoid:** Always use `Console(file=buf, force_terminal=True)` when capturing ANSI output to a string buffer.
**Warning signs:** Markdown output appears as plain text with no formatting.

### Pitfall 2: Eval loop infinite recursion
**What goes wrong:** AI generates code that calls `ai(...)` which generates code that calls `ai(...)`, creating an infinite loop.
**Why it happens:** The AI is instructed to produce code, and it has access to itself in the namespace.
**How to avoid:** Hard iteration limit (e.g., 5). Detect self-referential calls (`ai(` in generated code) and stop the loop. Log warnings when limit is hit.
**Warning signs:** REPL becomes unresponsive, token costs spike.

### Pitfall 3: Eval loop coroutine handling
**What goes wrong:** `async_exec` returns an unawaited coroutine for `await` expressions. If the eval loop doesn't await it, the AI gets `<coroutine object ...>` as output instead of the actual result.
**Why it happens:** `async_exec` was designed for the PY mode dispatch path where the caller (shell._dispatch) decides whether to await or fire-and-forget. The eval loop always needs the result.
**How to avoid:** In the eval loop, always check `asyncio.iscoroutine(result)` and `await` it if so. This is different from the shell's PY dispatch which fires via TaskManager.
**Warning signs:** AI feedback contains `<coroutine object ...>` strings.

### Pitfall 4: Session lock contention with concurrent AI calls
**What goes wrong:** Two concurrent `await ai("q1"), await ai("q2")` from PY mode try to use the same Claude CLI session, causing "session already in use" errors.
**Why it happens:** Claude CLI session files are locked by the running subprocess. Two subprocesses can't share a session ID.
**How to avoid:** Each concurrent call needs its own session. Options: (a) pool of session IDs, (b) generate a new session per call and track it, (c) serialize calls to the same session. Option (b) is simplest -- each `AI.__call__` that is concurrent gets a fresh session, while sequential calls reuse the session.
**Warning signs:** "already in use" errors from Claude CLI stderr.

### Pitfall 5: prompt_toolkit print_formatted_text vs patch_stdout
**What goes wrong:** `print_formatted_text(ANSI(...))` inside a background task (running under `patch_stdout`) may not display correctly if the ANSI string contains raw escape sequences that conflict with prompt_toolkit's internal rendering.
**Why it happens:** `patch_stdout` wraps sys.stdout with a proxy. `print_formatted_text` normally writes to the real terminal. When used from a background task, the output goes through the proxy.
**How to avoid:** The current code already uses `print_formatted_text` from `channels.py` inside `patch_stdout` successfully. The `ANSI` class is designed to work with this flow -- it parses escape sequences into prompt_toolkit's internal format before writing. Should work.
**Warning signs:** Garbled terminal output, broken prompt rendering.

### Pitfall 6: Cross-session context too large for first prompt
**What goes wrong:** Loading 50 recent entries from the store creates a context string that, combined with the namespace context and user prompt, exceeds reasonable prompt sizes or makes the first call slow.
**Why it happens:** Entries can be up to 10,000 chars each. 50 entries = 500K chars.
**How to avoid:** Cap cross-session context at a fixed character budget (e.g., 2000 chars, matching `MAX_CONTEXT_CHARS`). Truncate individual entries aggressively (first 100-200 chars). Filter out debug/internal entries.
**Warning signs:** First AI call takes unusually long, or AI response is confused by excessive context.

## Code Examples

### Verified: Rich Markdown to ANSI string
```python
# Source: Rich docs (https://rich.readthedocs.io/en/latest/markdown.html)
# + Console capture (https://rich.readthedocs.io/en/latest/console.html)
from io import StringIO
from rich.console import Console
from rich.markdown import Markdown

buf = StringIO()
console = Console(file=buf, width=80, force_terminal=True)
console.print(Markdown("# Hello\n\nThis is **bold** and `code`."))
ansi_output = buf.getvalue()
# ansi_output contains ANSI escape sequences for rendering
```

### Verified: prompt_toolkit ANSI class for display
```python
# Source: prompt_toolkit docs (https://python-prompt-toolkit.readthedocs.io/en/stable/pages/printing_text.html)
# + example: https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/print-text/ansi.py
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI

# Parse ANSI escape sequences from Rich and display
print_formatted_text(ANSI(ansi_output))
```

### Verified: Rich+prompt_toolkit bridge (combined)
```python
# Full bridge pattern
from io import StringIO
from rich.console import Console
from rich.markdown import Markdown
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI

def render_and_display_markdown(text: str, width: int = 80) -> None:
    """Render markdown through Rich, display through prompt_toolkit."""
    buf = StringIO()
    console = Console(file=buf, width=width, force_terminal=True)
    console.print(Markdown(text))
    print_formatted_text(ANSI(buf.getvalue()))
```

### Existing: Code extraction (already in codebase)
```python
# Source: bae/repl/ai.py line 23-26
_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```",
    re.DOTALL,
)
# AI.extract_code(text) returns list[str] of code block contents
```

### Existing: Code execution (already in codebase)
```python
# Source: bae/repl/exec.py
result, captured = await async_exec(code, namespace)
# result: last expression value or None
# captured: stdout output as string
# If await expression: result is an unawaited coroutine
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| AI as loop controller (Claude Code, Aider) | AI as callable object in shared namespace | Novel (cortex design) | AI code executes in the user's namespace, not a sandbox. Results are immediately available. |
| Separate markdown viewer (glow, mdcat) | Rich inline rendering | Rich 10+ (2020+) | No external binary needed, pure Python, works inside prompt_toolkit |
| IPython `_repr_markdown_` display | Rich Markdown + prompt_toolkit ANSI bridge | N/A | Works in any terminal, no IPython dependency |

**Deprecated/outdated:**
- Rich `Console.export_text()` for terminal display -- loses all formatting. Use `force_terminal=True` + StringIO instead.

## Open Questions

1. **Eval loop: should generated code execute in a try/except that captures tracebacks?**
   - What we know: `async_exec` propagates exceptions. The AI benefits from seeing tracebacks to self-correct.
   - What's unclear: Should ALL exceptions be caught and fed back, or should some (KeyboardInterrupt, SystemExit) propagate?
   - Recommendation: Catch all exceptions except CancelledError/KeyboardInterrupt/SystemExit. Feed traceback string back to AI as error output.

2. **Multi-session: should `ai` in namespace be a session manager or always point to the active session?**
   - What we know: `ai` is currently a single AI instance. Users call `await ai("question")`.
   - What's unclear: If `ai` becomes a session manager, does `await ai("question")` still work? Or does it need `await ai.session("1")("question")`?
   - Recommendation: `ai` in namespace always points to the ACTIVE session. `shell._ai_sessions` holds all sessions. Switching sessions updates `namespace["ai"]`. This preserves the existing API.

3. **Rich markdown rendering width: how to detect terminal width?**
   - What we know: Rich Console accepts a `width` parameter. `os.get_terminal_size().columns` gives current width.
   - What's unclear: Should the width be detected per-render (handles terminal resize) or fixed at startup?
   - Recommendation: Detect per-render. `os.get_terminal_size().columns` is fast and handles resize.

4. **Task menu scrollback: what replaces the toolbar display when menu is open?**
   - What we know: Currently, `_task_menu=True` replaces toolbar with task list. SC7 says print to scrollback instead.
   - What's unclear: Does the toolbar show normal content while the menu is printed above? Or is toolbar hidden?
   - Recommendation: Keep normal toolbar. Print the task list above the prompt (in scrollback). The `_task_menu` flag still gates digit keybindings for cancellation.

## Sources

### Primary (HIGH confidence)
- Rich Markdown docs: https://rich.readthedocs.io/en/latest/markdown.html
- Rich Console docs: https://rich.readthedocs.io/en/latest/console.html
- Rich PyPI (v14.3.2, Python 3.14): https://pypi.org/project/rich/
- prompt_toolkit printing docs: https://python-prompt-toolkit.readthedocs.io/en/stable/pages/printing_text.html
- prompt_toolkit ANSI example: https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/print-text/ansi.py
- Existing codebase: `bae/repl/ai.py`, `bae/repl/exec.py`, `bae/repl/channels.py`, `bae/repl/store.py`, `bae/repl/shell.py`, `bae/repl/toolbar.py`

### Secondary (MEDIUM confidence)
- Claude CLI session management: https://code.claude.com/docs/en/headless
- Rich+ANSI capture discussion: https://github.com/Textualize/rich/discussions/2648
- prompt_toolkit patch_stdout: https://github.com/prompt-toolkit/python-prompt-toolkit/blob/main/examples/prompts/patch-stdout.py

### Tertiary (LOW confidence)
- AI eval loop patterns (ReAct): https://www.siddharthbharath.com/build-a-coding-agent-python-tutorial/ -- general pattern, adapted for cortex's subprocess-based AI

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Rich is well-established, prompt_toolkit ANSI bridge is documented and tested
- Architecture: HIGH - All building blocks exist in codebase, eval loop pattern is well-understood
- Pitfalls: HIGH - Identified from actual codebase behavior (force_terminal, coroutine handling, session locks)
- Multi-session: MEDIUM - Novel design, no prior art in this codebase, but straightforward dict-of-instances pattern

**Research date:** 2026-02-14
**Valid until:** 2026-03-14 (stable domain, Rich and prompt_toolkit are mature)
