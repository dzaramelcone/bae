# Phase 24: Execution Display - Research

**Researched:** 2026-02-14
**Domain:** Rich Panel rendering for AI code execution display via ViewFormatter, with buffered grouping and deduplication
**Confidence:** HIGH

## Summary

Phase 24 implements a concrete `UserView` formatter that plugs into the ViewFormatter protocol added in Phase 23. The scope is: (1) create `bae/repl/views.py` with a `UserView` class, (2) wire it to the `py` channel's `_formatter` field in `CortexShell.__init__`, and (3) render AI-executed code in Rich Panels with syntax highlighting, output in a separate panel below, grouped as a visual unit via buffered rendering, and suppress the redundant `[py]` echo.

The critical insight is that `UserView` only needs to handle metadata types `"ai_exec"` and `"ai_exec_result"` specially. All other `py` channel writes (`"stdout"`, `"expr_result"`, `"warning"`, `"error"`, `"tool_translated"`, `"tool_result"`) fall through to the existing line-by-line display. This is NOT a wholesale replacement of `py` channel display -- it is surgical Panel rendering for exactly two metadata types, with a buffer to group them.

Zero new dependencies. Rich 14.3.2 (installed) provides Panel, Syntax, Group, Rule, Text, box. prompt_toolkit 3.0.52 (installed) provides ANSI, print_formatted_text. The Console(file=StringIO()) bridge is already proven in `render_markdown()`. All four Rich rendering approaches (code Panel, output Panel, grouped Panel, and the ANSI bridge) have been verified locally with the installed versions.

**Primary recommendation:** Create `views.py` with a `UserView` class that buffers `ai_exec` writes and flushes grouped code+output panels on `ai_exec_result`. Wire it to the `py` channel in shell.py. The `ai` channel does NOT get this formatter -- AI markdown responses continue to render via the existing `Channel._display()` markdown path.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `rich.panel.Panel` | 14.3.2 (installed) | Framed border around code and output | Already used concept in codebase, proven rendering path |
| `rich.syntax.Syntax` | 14.3.2 (installed) | Python syntax highlighting inside panels | Rich's built-in syntax highlighter, uses Pygments internally |
| `rich.console.Console` | 14.3.2 (installed) | Renders Rich objects to ANSI string via StringIO | Already proven in `render_markdown()` at channels.py:30-40 |
| `rich.console.Group` | 14.3.2 (installed) | Combines multiple renderables in one Panel | Enables code+rule+output inside a single panel border |
| `rich.text.Text` | 14.3.2 (installed) | Wraps plain text as Rich renderable | Used for output text inside grouped panel |
| `rich.rule.Rule` | 14.3.2 (installed) | Horizontal divider between code and output | Visual separator inside grouped panel |
| `rich.box` | 14.3.2 (installed) | Box style for panel borders (ROUNDED) | Configurable border characters |
| `prompt_toolkit.formatted_text.ANSI` | 3.0.52 (installed) | Converts ANSI string to prompt_toolkit FormattedText | Already used in `render_markdown()` bridge |
| `prompt_toolkit.print_formatted_text` | 3.0.52 (installed) | patch_stdout-safe terminal output | Already the only safe way to write to terminal |

### Supporting

No additional libraries needed. Phase 24 uses only what is already installed and imported.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Two separate panels (code + output) | Single grouped panel with Rule separator | Grouped panel is visually tighter and satisfies DISP-03 "single visual unit". Two panels leave a gap between them where other channel output could interleave. Use grouped panel. |
| Rich `Syntax` with monokai theme | `Syntax` with ansi_dark theme | monokai has a dark background that contrasts well in terminals. ansi_dark uses the terminal's native colors. monokai is more visually distinct for "this is AI-executed code." |
| `box.ROUNDED` | `box.SIMPLE` or `box.HEAVY` | ROUNDED uses unicode curved corners, looks clean in modern terminals. SIMPLE is too minimal. HEAVY is too visually loud. |

**Installation:** None. Zero new dependencies.

## Architecture Patterns

### Recommended Structure

```
bae/repl/
  views.py        NEW  -- UserView concrete formatter + _rich_to_ansi helper
  channels.py     UNCHANGED -- ViewFormatter protocol already exists
  ai.py           UNCHANGED -- metadata types already correct
  shell.py        MODIFIED -- wire UserView to py channel _formatter
```

One new file, one small modification. The `ai.py` eval loop already writes the correct metadata types (`"ai_exec"` and `"ai_exec_result"`) -- no changes needed there.

### Pattern 1: Metadata-Dispatched Rendering

**What:** UserView.render() dispatches on `metadata["type"]` to choose rendering strategy.
**When:** Every `py` channel write goes through the formatter.
**Why:** The producer (AI eval loop, shell dispatch) already tags writes with metadata. The formatter trusts the tag instead of parsing content.

```python
# Source: Architecture pattern from Phase 23 research, verified with codebase metadata analysis
class UserView:
    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        content_type = meta.get("type", "")

        if content_type == "ai_exec":
            self._buffer_exec(content, meta)
            return
        if content_type == "ai_exec_result":
            self._flush_exec(content, meta)
            return
        # All other py channel writes: existing line-by-line rendering
        self._render_prefixed(channel_name, color, content, meta)
```

### Pattern 2: Buffered Exec Grouping

**What:** `ai_exec` content is buffered (not rendered). When `ai_exec_result` arrives, both are rendered as a single grouped panel.
**When:** The eval loop always writes `ai_exec` immediately followed by `ai_exec_result` in the same coroutine with no interleaving possible.
**Why:** DISP-03 requires code and output to appear as a single visual unit. Without buffering, they would render as two separate panel outputs with other channel writes possibly appearing between them.

```python
def _buffer_exec(self, code, meta):
    """Buffer code, wait for output to arrive."""
    self._pending_code = code
    self._pending_meta = meta

def _flush_exec(self, output, meta):
    """Render buffered code + output as grouped panel."""
    code = self._pending_code
    self._pending_code = None
    self._pending_meta = None

    if code is None:
        # Orphaned output -- shouldn't happen, but render safely
        self._render_output_panel(output, meta)
        return

    self._render_grouped_panel(code, output, meta)
```

**Safety:** The eval loop in `ai.py:148-167` always writes `ai_exec` then `ai_exec_result` atomically. Between those two writes, no `await` occurs -- just `async_exec` (whose output is captured, not printed) and `repr()`. No other coroutine can interleave a write to the same channel. The buffer is safe.

### Pattern 3: Rich-to-ANSI Bridge (Existing, Reused)

**What:** All Rich rendering goes through `Console(file=StringIO(), force_terminal=True)` then `print_formatted_text(ANSI(...))`.
**When:** Every panel render call.
**Why:** prompt_toolkit's `patch_stdout` requires all terminal output to go through prompt_toolkit. Direct `Console.print()` to stdout corrupts the prompt.
**Source:** `channels.py:30-40` (`render_markdown()`) -- already proven in production.

```python
def _rich_to_ansi(renderable, width=None):
    """Render a Rich renderable to ANSI string for prompt_toolkit."""
    if width is None:
        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 80
    buf = StringIO()
    console = Console(file=buf, width=width, force_terminal=True)
    console.print(renderable)
    return buf.getvalue()
```

### Pattern 4: Fallback to Default Display

**What:** For metadata types the formatter does not handle specially (`"stdout"`, `"expr_result"`, `"warning"`, `"error"`, `"tool_translated"`, `"tool_result"`, and writes with no metadata), UserView renders the standard color-coded `[channel] content` prefix lines.
**When:** User-typed Python code produces output, errors, or the AI's tool-translated calls.
**Why:** DISP-01 through DISP-04 only concern AI-INITIATED code execution. User-typed code continues to render as `[py] x = 42`.

```python
def _render_prefixed(self, channel_name, color, content, meta):
    """Fall back to the standard line-by-line display with channel prefix."""
    label = f"[{channel_name}]"
    if meta and "label" in meta:
        label = f"[{channel_name}:{meta['label']}]"
    for line in content.splitlines():
        text = FormattedText([
            (f"{color} bold", label),
            ("", " "),
            ("", line),
        ])
        print_formatted_text(text)
```

### Anti-Patterns to Avoid

- **Rich Console writing to stdout directly:** Always `Console(file=StringIO())`. Never `Console()`. The prompt_toolkit `patch_stdout` context manager only intercepts writes that go through prompt_toolkit's API. Direct stdout writes corrupt the prompt display. Source: Pitfalls research, Pitfall 8.

- **Nesting pre-rendered ANSI inside Rich Panel:** Never call `render_markdown(text)` first and then wrap the ANSI string in a Panel. The ANSI escape codes count as characters, inflating width calculations. The Panel MUST wrap the Rich Markdown/Syntax object, not the ANSI string. Source: Pitfalls research, Pitfall 1.

- **Formatter modifying content:** The formatter renders content as-is. Syntax highlighting and panel borders are additive framing. The content string passed to `render()` is the same content stored in SessionStore. No stripping, no transformation. Source: Architecture research, Anti-Pattern 4.

- **Setting formatter on the `ai` channel:** Only the `py` channel gets UserView. The `ai` channel's markdown rendering continues through the existing `Channel._display()` path with `markdown=True`. Setting a formatter on `ai` would require reimplementing markdown rendering inside UserView -- unnecessary duplication for Phase 24.

- **Rendering empty output panels:** When `ai_exec_result` content is `"(no output)"`, skip the output portion of the grouped panel. Show only the code panel. Source: Pitfalls research, Pitfall 12.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Syntax highlighting | Custom ANSI escape code generator for Python | `rich.syntax.Syntax` | Pygments integration, theme support, handles all edge cases (strings, f-strings, decorators) |
| Terminal-safe border drawing | Manual box-drawing characters | `rich.panel.Panel` with `rich.box` | Handles width, wrapping, padding, title positioning |
| ANSI string from Rich objects | Manual Console setup each time | `_rich_to_ansi()` helper function | Centralizes width detection, StringIO buffer, force_terminal flag |
| Content grouping in one frame | Custom multi-part rendering | `rich.console.Group` | Composes arbitrary renderables; handles internal width delegation |
| Fallback prefix display | Reimplementing Channel._display logic | Copy the exact FormattedText pattern from channels.py:118-125 | Must match existing behavior exactly for non-AI writes |

**Key insight:** Rich already solves every rendering problem. The value of Phase 24 is wiring metadata-driven dispatch and buffered grouping, not rendering primitives.

## Common Pitfalls

### Pitfall 1: ANSI Contamination in Nested Rich Rendering

**What goes wrong:** Pre-rendering content to ANSI then wrapping in a Panel produces garbled output. ANSI escapes are counted as characters by Panel's width calculator.
**Why it happens:** Rich calculates Panel content width by counting visible characters. Pre-rendered ANSI sequences are invisible but counted.
**How to avoid:** Always compose Rich renderables in a single tree: `Panel(Syntax(code))`, never `Panel(render_to_ansi(Syntax(code)))`. The `_rich_to_ansi()` call happens ONCE at the outermost level.
**Warning signs:** Panel right border misplaced or content overflowing the frame.

### Pitfall 2: Forgetting Fallback for Non-AI Writes

**What goes wrong:** UserView on the `py` channel intercepts ALL `py` writes, including user-typed Python code results. If the formatter only handles `ai_exec` and `ai_exec_result`, user writes silently disappear.
**Why it happens:** The formatter receives every write to the channel, not just AI-originated ones.
**How to avoid:** The `render()` method MUST have a fallback branch that renders standard `[py] content` prefix lines for any metadata type it does not handle specially. Test with user PY mode writes after wiring the formatter.
**Warning signs:** User types `2 + 2` in PY mode and sees nothing.

### Pitfall 3: Buffer Not Flushed on Missing ai_exec_result

**What goes wrong:** If `ai_exec` is written but `ai_exec_result` never comes (e.g., `async_exec` raises `CancelledError`), the buffered code is never flushed. The next `ai_exec` write finds stale state in the buffer.
**Why it happens:** Cancellation or `SystemExit` bypasses the `ai_exec_result` write in `ai.py:159-163`.
**How to avoid:** When `_buffer_exec` is called and `_pending_code is not None`, flush the stale pending code as a standalone code panel before buffering the new one. This handles the edge case of interrupted execution.
**Warning signs:** Panel from a previous exec appearing with the next exec's output.

### Pitfall 4: UserView Not Wired in Tests

**What goes wrong:** Tests create `Channel(name="py", color="#87ff87")` without setting `_formatter`. Phase 24 code works in the REPL (where shell.py wires it) but tests fall back to the old display path, masking bugs.
**Why it happens:** The test fixtures from `test_channels.py` create bare channels.
**How to avoid:** Phase 24 tests must explicitly create `UserView` instances and assign them to `channel._formatter`. Test both the formatter in isolation AND the integration of formatter-on-channel.
**Warning signs:** Tests pass but REPL rendering is broken.

### Pitfall 5: Terminal Width Not Captured Per-Render

**What goes wrong:** Caching terminal width at module load time produces wrong-width panels after terminal resize.
**Why it happens:** `os.get_terminal_size()` is called once at import time instead of per-render.
**How to avoid:** Call `os.get_terminal_size()` inside `_rich_to_ansi()` on every render call. This matches the existing pattern in `render_markdown()` at channels.py:33-35.
**Warning signs:** Panels stay the wrong width after resizing the terminal window.

## Code Examples

Verified patterns from local Rich 14.3.2 execution tests:

### _rich_to_ansi Helper

```python
# views.py
import os
from io import StringIO
from rich.console import Console


def _rich_to_ansi(renderable, width=None):
    """Render a Rich renderable to ANSI string for prompt_toolkit."""
    if width is None:
        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 80
    buf = StringIO()
    console = Console(file=buf, width=width, force_terminal=True)
    console.print(renderable)
    return buf.getvalue()
```

Source: Generalized from `render_markdown()` in `channels.py:30-40`. Verified locally.

### UserView Class

```python
# views.py
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI, FormattedText
from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text


class UserView:
    """Framed panel display for AI code execution on [py] channel.

    Buffers ai_exec writes, renders grouped code+output panels on ai_exec_result.
    All other py channel writes fall through to standard prefix display.
    """

    def __init__(self):
        self._pending_code: str | None = None
        self._pending_meta: dict | None = None

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        content_type = meta.get("type", "")

        if content_type == "ai_exec":
            # Flush stale buffer if present (interrupted previous exec)
            if self._pending_code is not None:
                self._render_code_panel(self._pending_code, self._pending_meta or {})
            self._pending_code = content
            self._pending_meta = meta
            return

        if content_type == "ai_exec_result" and self._pending_code is not None:
            self._render_grouped_panel(self._pending_code, content, self._pending_meta or {})
            self._pending_code = None
            self._pending_meta = None
            return

        # Fallback: standard prefix display for all other write types
        self._render_prefixed(channel_name, color, content, meta)

    def _render_grouped_panel(self, code, output, meta):
        """Render code + output as a single framed panel."""
        label = meta.get("label", "")
        title = f"ai:{label}" if label else "exec"

        parts = [Syntax(code, "python", theme="monokai")]
        if output and output != "(no output)":
            parts.append(Rule(style="dim"))
            parts.append(Text(output))

        panel = Panel(
            Group(*parts),
            title=f"[bold cyan]{title}[/]",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        ansi = _rich_to_ansi(panel)
        print_formatted_text(ANSI(ansi))

    def _render_code_panel(self, code, meta):
        """Render code-only panel (when output was never received)."""
        label = meta.get("label", "")
        title = f"ai:{label}" if label else "exec"

        panel = Panel(
            Syntax(code, "python", theme="monokai"),
            title=f"[bold cyan]{title}[/]",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        ansi = _rich_to_ansi(panel)
        print_formatted_text(ANSI(ansi))

    def _render_prefixed(self, channel_name, color, content, meta):
        """Standard line-by-line display with channel prefix."""
        label = f"[{channel_name}]"
        if meta and "label" in meta:
            label = f"[{channel_name}:{meta['label']}]"
        for line in content.splitlines():
            text = FormattedText([
                (f"{color} bold", label),
                ("", " "),
                ("", line),
            ])
            print_formatted_text(text)
```

Source: Composed from verified Rich rendering tests and existing `_display()` logic in `channels.py:98-125`.

### Wiring UserView to py Channel in Shell

```python
# In shell.py CortexShell.__init__, after channel registration:
from bae.repl.views import UserView

# After router.register loop:
self.router.py._formatter = UserView()
```

Source: Phase 23 established `_formatter` field on Channel. Direct attribute access is the pattern used in tests (`test_channels.py:405`).

### Test: UserView Buffers ai_exec and Flushes on ai_exec_result

```python
def test_user_view_groups_exec_and_result():
    """ai_exec is buffered, ai_exec_result triggers grouped panel render."""
    view = UserView()
    with patch("bae.repl.views.print_formatted_text") as mock_pft:
        # First call: buffer code, no output
        view.render("py", "#87ff87", "x = 42", metadata={"type": "ai_exec", "label": "1"})
        mock_pft.assert_not_called()

        # Second call: flush grouped panel
        view.render("py", "#87ff87", "42", metadata={"type": "ai_exec_result", "label": "1"})
        mock_pft.assert_called_once()
        # The call should be ANSI (from Rich Panel rendering)
        arg = mock_pft.call_args[0][0]
        assert isinstance(arg, ANSI)
```

### Test: UserView Falls Through for User-Typed Code

```python
@patch("bae.repl.views.print_formatted_text")
def test_user_view_fallback_for_user_code(mock_pft):
    """Non-AI writes render with standard prefix display."""
    view = UserView()
    view.render("py", "#87ff87", "hello", metadata={"type": "stdout"})
    mock_pft.assert_called_once()
    fragments = list(mock_pft.call_args[0][0])
    assert fragments[0] == ("#87ff87 bold", "[py]")
    assert fragments[2] == ("", "hello")
```

### Test: Deduplication (DISP-04) - ai_exec Suppressed from Flat Display

```python
def test_user_view_suppresses_ai_exec_echo():
    """ai_exec type is buffered, NOT rendered as [py] prefix line."""
    view = UserView()
    with patch("bae.repl.views.print_formatted_text") as mock_pft:
        view.render("py", "#87ff87", "x = 42", metadata={"type": "ai_exec", "label": "1"})
        # No print_formatted_text call -- code is buffered
        mock_pft.assert_not_called()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `[py] code` flat prefix lines for AI exec | Rich Panel with Syntax highlighting | Phase 24 (this phase) | AI code execution visually distinct from user code |
| Code and output as separate channel writes | Buffered rendering as grouped visual unit | Phase 24 (this phase) | No interleaving between code and its output |
| Redundant `[py] code` echo of AI's code | Suppressed via formatter (code rendered only in panel) | Phase 24 (this phase) | Eliminates duplicate display of the same code |
| One display path for all `py` writes | Metadata-dispatched rendering (ai_exec vs user code) | Phase 24 (this phase) | Different visual treatment for different content sources |

**Deprecated/outdated:**
- Nothing deprecated. The fallback path in UserView reproduces the existing `_display()` behavior exactly. Channels without a formatter continue unchanged.

## Open Questions

1. **Should UserView also be set on the `ai` channel?**
   - What we know: The `ai` channel has `markdown=True` and renders through `render_markdown()`. AI responses include code blocks that the user sees in the markdown rendering. Setting a formatter on `ai` would override the markdown path entirely.
   - What's unclear: Whether the AI response's code block (in markdown) and the `[py]` exec panel feel redundant together.
   - Recommendation: Do NOT set formatter on `ai` channel in Phase 24. The AI markdown rendering works well. The `[py]` exec panel shows the EXECUTION RESULT, which the markdown does not. Revisit if UAT reveals visual clutter.

2. **Should `(no output)` still render a panel?**
   - What we know: When `async_exec` returns `(None, "")` (pure assignment, no expression result), the eval loop writes `output = "(no output)"`. Rendering an empty-looking panel feels wrong.
   - What's unclear: Whether suppressing the output portion is sufficient or if the code panel should also be suppressed for no-output cases.
   - Recommendation: For `"(no output)"`, render a code-only panel (no Rule separator, no output section). The user sees the code was executed but with no visible result -- which is accurate.

3. **Should tool_translated and tool_result also get panel treatment?**
   - What we know: Tool call translation (Phase 22) writes `"tool_translated"` and `"tool_result"` to the `py` channel. These are AI-initiated reads/writes/greps.
   - What's unclear: Whether users expect these to look like exec panels too.
   - Recommendation: Defer. Keep tool_translated and tool_result on the fallback prefix display path for Phase 24. Phase 25 or a future phase can add panel treatment if desired.

## Sources

### Primary (HIGH confidence)
- `bae/repl/channels.py` -- ViewFormatter protocol (lines 43-61), Channel._formatter (line 73), _display() delegation (lines 105-107), render_markdown bridge (lines 30-40)
- `bae/repl/ai.py` -- Eval loop code+output writes (lines 165-167), metadata types `ai_exec` and `ai_exec_result`
- `bae/repl/shell.py` -- py channel metadata types: `stdout`, `expr_result`, `warning`, `error` (lines 360-401)
- `tests/repl/test_channels.py` -- 45 tests including ViewFormatter delegation tests (lines 389-444)
- `tests/repl/test_ai.py` -- Eval loop tee tests verifying ai_exec and ai_exec_result metadata (lines 443-486)
- `.planning/phases/23-view-framework/23-RESEARCH.md` -- ViewFormatter protocol design, Rich-to-ANSI bridge pattern
- `.planning/research/ARCHITECTURE.md` -- Execution display flow, UserView design, buffered exec grouping
- `.planning/research/PITFALLS.md` -- Pitfalls 1 (ANSI contamination), 5 (dedup removing results), 6 (width desync), 8 (patch_stdout bypass), 12 (empty frames)
- Local execution: Rich 14.3.2 Panel + Syntax + Group rendering verified with Console(file=StringIO()) and prompt_toolkit ANSI parse

### Secondary (MEDIUM confidence)
- [Rich Panel docs](https://rich.readthedocs.io/en/stable/panel.html) -- Panel API, titles, subtitles, border styles
- [Rich Syntax docs](https://rich.readthedocs.io/en/stable/syntax.html) -- Syntax highlighter API, themes
- [Rich Group docs](https://rich.readthedocs.io/en/stable/group.html) -- Group renderable for composing multiple objects in one Panel
- [Rich Console API](https://rich.readthedocs.io/en/stable/console.html) -- Console(file=StringIO()) for ANSI capture
- [Rich + prompt_toolkit rendering discussion](https://github.com/Textualize/rich/discussions/936) -- Bridge pattern validation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all Rich APIs verified locally with installed version 14.3.2
- Architecture: HIGH -- metadata types already exist in eval loop, ViewFormatter protocol proven in Phase 23, buffered grouping verified safe (no interleaving possible)
- Pitfalls: HIGH -- all pitfalls catalogued from prior research (PITFALLS.md) with codebase-specific evidence

**Research date:** 2026-02-14
**Valid until:** Indefinite -- internal architecture over stable Rich 14.x and prompt_toolkit 3.x. No external version sensitivity.
