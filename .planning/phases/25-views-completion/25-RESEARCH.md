# Phase 25: Views Completion - Research

**Researched:** 2026-02-14
**Domain:** DebugView + AISelfView formatters, runtime view toggling via keybinding, toolbar view indicator
**Confidence:** HIGH

## Summary

Phase 25 completes the multi-view system by adding two new ViewFormatter implementations (DebugView and AISelfView), a keybinding to cycle between views at runtime, and a toolbar widget showing the active view mode. The foundation is solid: Phase 23 established the ViewFormatter protocol and Channel._formatter delegation, Phase 24 proved the pattern with UserView (buffered exec grouping, metadata dispatch, fallback prefix display).

The three requirements (VIEW-04, VIEW-05, VIEW-06) map cleanly to three deliverables: DebugView renders raw channel data with full metadata visible for debugging. AISelfView provides structured feedback that the eval loop can consume (showing what the AI "sees" -- prompts sent, execution results, tool outputs). The view toggle cycles all channels' formatters simultaneously via Ctrl+V, with a toolbar widget indicating the active view.

The implementation is straightforward because all the hard problems are solved. The `_rich_to_ansi()` helper exists. The formatter protocol is defined. The UserView reference implementation demonstrates the metadata-dispatch pattern. DebugView and AISelfView are simpler than UserView (no buffering needed). The toggle mechanism is a per-channel `_formatter` swap on each channel in the router, following the existing Shift+Tab mode-cycling pattern in `_build_key_bindings()`.

**Primary recommendation:** Add DebugView and AISelfView to `views.py`, add a ViewMode enum and `_set_view()` method to CortexShell, wire Ctrl+V keybinding, add a view widget to toolbar. Three files modified (`views.py`, `shell.py`, `toolbar.py`), one test file modified (`test_views.py`), one new test file possible (`test_toolbar.py` already exists).

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `typing.Protocol` | stdlib (3.14) | ViewFormatter protocol (already defined) | Already in use in channels.py |
| `rich.panel.Panel` | 14.3.2 (installed) | DebugView metadata panel, AISelfView prompt panel | Already used in UserView |
| `rich.syntax.Syntax` | 14.3.2 (installed) | DebugView code highlighting | Already used in UserView |
| `rich.text.Text` | 14.3.2 (installed) | Styled text renderables | Already used in UserView |
| `rich.console.Console` | 14.3.2 (installed) | Rich-to-StringIO rendering | Already used in `_rich_to_ansi()` |
| `rich.box` | 14.3.2 (installed) | Panel border styles | Already used in UserView |
| `prompt_toolkit.formatted_text.ANSI` | 3.0.52 (installed) | ANSI string to FormattedText | Already used in views.py |
| `prompt_toolkit.formatted_text.FormattedText` | 3.0.52 (installed) | Styled text for prefix display | Already used in views.py |
| `prompt_toolkit.print_formatted_text` | 3.0.52 (installed) | patch_stdout-safe output | Already used everywhere |
| `enum.Enum` | stdlib | ViewMode enum | Already used for Mode in modes.py |

### Supporting

No additional libraries needed. Phase 25 uses only what is already installed and imported.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ViewMode enum in shell.py | ViewMode in a new modes.py or views.py | Keeping view mode state with the shell makes sense since the shell owns the keybinding and toolbar. But the enum itself could live in views.py alongside the formatters it represents. Either works. Put it in views.py to keep shell.py lean. |
| Per-channel formatter swap | Global formatter on ChannelRouter | Architecture docs explicitly rejected global formatter (Phase 23 research). Per-channel swap allows future flexibility. The toggle sets formatter on each channel individually. |
| Ctrl+V keybinding | Ctrl+D or other | Ctrl+V is mnemonic for "View". Ctrl+D is EOF in most terminals. Ctrl+V is "paste" in some terminals but prompt_toolkit intercepts it. Check: prompt_toolkit handles Ctrl+V as literal-insert ("quoted-insert" in readline terms). Using `"c-v"` in prompt_toolkit key bindings will capture it before the terminal processes it, which is fine but means the user loses quoted-insert. This is acceptable -- quoted-insert is rarely needed in this REPL context. |

**Installation:** None. Zero new dependencies.

## Architecture Patterns

### Current State (Post Phase 23+24)

```
bae/repl/
  channels.py     -- ViewFormatter protocol, Channel._formatter field, _display() delegation
  views.py         -- UserView concrete formatter, _rich_to_ansi helper
  shell.py         -- CortexShell, UserView wired to py channel
  toolbar.py       -- ToolbarConfig, make_mode_widget, make_tasks_widget, etc.
  modes.py         -- Mode enum, MODE_CYCLE, MODE_COLORS
```

### Phase 25 Changes

```
bae/repl/
  views.py         MODIFIED  -- Add DebugView, AISelfView, ViewMode enum, VIEW_FORMATTERS dict
  shell.py         MODIFIED  -- Add view_mode state, _set_view() method, Ctrl+V keybinding, toolbar view widget
  toolbar.py       MODIFIED  -- Add make_view_widget() factory
  channels.py      UNCHANGED
  modes.py         UNCHANGED
tests/repl/
  test_views.py    MODIFIED  -- Tests for DebugView, AISelfView, ViewMode, view switching
  test_toolbar.py  MODIFIED  -- Test for make_view_widget
```

### Pattern 1: Metadata-Dump Rendering (DebugView)

**What:** DebugView renders ALL metadata fields as a visible header, followed by raw content. No Rich Panel wrapping -- plain prefix lines with metadata visible.
**When:** User activates debug view to see what metadata the eval loop is producing.
**Why:** The UserView hides metadata (dispatching on it silently). Debug users need to see what type, label, and other metadata fields are being set, to diagnose display or eval loop issues.

```python
class DebugView:
    """Raw content with full metadata for debugging."""

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        # Header line with all metadata keys
        meta_str = " ".join(f"{k}={v}" for k, v in meta.items())
        header = f"[{channel_name}] {meta_str}" if meta_str else f"[{channel_name}]"
        text = FormattedText([(f"{color} bold", header)])
        print_formatted_text(text)
        # Raw content, no markdown rendering, no panels
        for line in content.splitlines():
            text = FormattedText([
                ("fg:#808080", "  "),
                ("", line),
            ])
            print_formatted_text(text)
```

**Key design decision:** DebugView does NOT use Rich Panels or Syntax highlighting. It shows raw content as-is. This is intentional -- the debug view is for seeing exactly what data flows through channels, not for pretty rendering.

### Pattern 2: Structured Feedback Rendering (AISelfView)

**What:** AISelfView shows what the AI "sees" in the eval loop -- the prompts, feedback, and context that shape its responses. For `ai` channel writes, it renders the raw response text dimmed. For `py` channel writes with `ai_exec` type, it renders the code and result as structured feedback (the format the eval loop feeds back to the AI).
**When:** User wants to understand why the AI is behaving a certain way.
**Why:** The UserView shows polished panels. The AISelfView shows the raw data pipeline from the AI's perspective.

The AISelfView needs to show:
- What the AI said (response text) -- rendered as-is, dimmed
- What code was executed (ai_exec) -- shown with a `[exec]` prefix
- What output was produced (ai_exec_result) -- shown with `[output]` prefix
- Tool translations (tool_translated, tool_result) -- shown with `[tool]` prefix
- The feedback that goes back to the AI -- this is the key differentiator

```python
class AISelfView:
    """Shows AI perspective: what the eval loop sends and receives."""

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        content_type = meta.get("type", "")

        if content_type == "response":
            # AI response -- show dimmed (this is what the AI produced)
            label = meta.get("label", "")
            header = f"[ai:{label}] response" if label else "[ai] response"
            _print_dim_header(header)
            _print_dim_content(content)
        elif content_type == "ai_exec":
            _print_dim_header("[exec]")
            _print_dim_content(content)
        elif content_type == "ai_exec_result":
            _print_dim_header("[output]")
            _print_dim_content(content)
        elif content_type in ("tool_translated", "tool_result"):
            tag = "[tool]" if content_type == "tool_translated" else "[tool:result]"
            _print_dim_header(tag)
            _print_dim_content(content)
        else:
            # All other writes: standard prefix display
            self._render_prefixed(channel_name, color, content, meta)
```

**Key design decision:** AISelfView does NOT buffer or group. Every write renders immediately. The point is to show the sequential data flow, not to present a polished view. The eval loop's feedback format is already structured (see ai.py lines 174-183: `"[Output]\n{output}"` and multi-block notices).

### Pattern 3: View Mode Cycling (Shell)

**What:** CortexShell holds a `view_mode` state. Ctrl+V cycles through ViewMode values. On each cycle, `_set_view()` updates `_formatter` on every channel in the router.
**When:** User presses Ctrl+V at any time during the REPL session.
**Why:** Views are a presentation concern. Switching views does not affect data recording (store) or buffering -- only how `_display()` renders content.

```python
# In views.py
class ViewMode(Enum):
    USER = "user"
    DEBUG = "debug"
    AI_SELF = "ai-self"

VIEW_CYCLE = [ViewMode.USER, ViewMode.DEBUG, ViewMode.AI_SELF]

VIEW_FORMATTERS = {
    ViewMode.USER: UserView,      # class, instantiated per-switch
    ViewMode.DEBUG: DebugView,
    ViewMode.AI_SELF: AISelfView,
}
```

```python
# In shell.py CortexShell
def _set_view(self, mode: ViewMode) -> None:
    """Switch all channels to the given view mode."""
    self.view_mode = mode
    formatter = VIEW_FORMATTERS[mode]()
    for ch in self.router._channels.values():
        ch._formatter = formatter
```

**Key design decision:** Each view switch creates a NEW formatter instance. UserView has buffer state (`_pending_code`, `_pending_meta`). Reusing a stale UserView after switching to debug and back could have orphaned buffer state. Fresh instances are clean. DebugView and AISelfView are stateless, so fresh instances are trivially safe.

**Keybinding integration:**

```python
# In _build_key_bindings()
@kb.add("c-v")
def cycle_view(event):
    """Ctrl+V cycles view modes."""
    idx = VIEW_CYCLE.index(shell.view_mode)
    shell.view_mode = VIEW_CYCLE[(idx + 1) % len(VIEW_CYCLE)]
    shell._set_view(shell.view_mode)
    event.app.invalidate()
```

This follows the exact pattern of the existing Shift+Tab mode cycling (shell.py lines 117-122).

### Pattern 4: Toolbar View Widget

**What:** A toolbar widget showing the active view mode, visible only when not in user view (since user view is the default).
**When:** Always rendered in toolbar, but returns empty list when view_mode is USER (to avoid clutter).
**Why:** Users need to know they are in a non-default view. The mode widget shows NL/PY/GRAPH/BASH. The view widget shows user/debug/ai-self.

```python
# In toolbar.py
def make_view_widget(shell) -> ToolbarWidget:
    """Built-in widget: active view mode (hidden when user view)."""
    def widget():
        if shell.view_mode.value == "user":
            return []
        return [("class:toolbar.view", f" {shell.view_mode.value} ")]
    return widget
```

### Anti-Patterns to Avoid

- **DebugView Using Rich Panels:** Debug view must show RAW data. Wrapping metadata in panels defeats the purpose. Use plain FormattedText only.

- **AISelfView Modifying Content:** The view must not strip, transform, or enrich content. It renders what the channel receives. The "AI perspective" framing is in the HEADERS, not in content transformation.

- **Shared Formatter Instance Across Views:** Do not reuse a UserView instance after switching to debug and back. UserView has buffer state that could be stale. Always create fresh instances on view switch.

- **Setting Formatter to None for "Default" View:** The current code path when `_formatter is None` runs the legacy `_display()` code. This is NOT the UserView -- it is the pre-Phase-23 behavior. The USER view mode should set a `UserView()` formatter, not set `_formatter = None`. This ensures consistent behavior through the formatter protocol.

- **Ctrl+V Conflicting With Paste:** In some terminal emulators, Ctrl+V is paste. prompt_toolkit intercepts key events before the terminal processes them, so `@kb.add("c-v")` will work. But be aware: if Dzara uses a terminal where Ctrl+V paste is important, the keybinding choice may need revisiting. The architecture research suggested Ctrl+V as the mnemonic.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rich-to-ANSI bridge | Manual Console setup per formatter | `_rich_to_ansi()` in views.py | Already exists, centralized, handles width detection and StringIO |
| Prefix display fallback | Per-view reimplementation | Copy `_render_prefixed()` from UserView or extract as shared function | Exact same logic needed in DebugView fallback for non-debug channels |
| View mode state management | Custom state machine | Simple enum + dict lookup | Three states, no transitions, no guards -- enum suffices |
| Terminal output safety | Per-formatter StringIO handling | Always use `print_formatted_text()` from prompt_toolkit | Enforced by existing pattern -- never write to stdout directly |

**Key insight:** Phase 25 is a composition phase. All primitives exist (ViewFormatter protocol, `_rich_to_ansi()`, Channel._formatter, keybinding infrastructure, toolbar widgets). The work is wiring them together, not building new infrastructure.

## Common Pitfalls

### Pitfall 1: UserView Buffer State After View Toggle

**What goes wrong:** User is in USER view. AI writes `ai_exec` (buffered in UserView). User presses Ctrl+V to switch to DEBUG. The old UserView instance is replaced. The buffered code is lost -- when `ai_exec_result` arrives, the new formatter (DebugView) has no pending code.
**Why it happens:** UserView buffers `ai_exec` writes. Switching views mid-buffer creates an orphaned state.
**How to avoid:** When `_set_view()` replaces formatters, check if the outgoing formatter is a UserView with pending code. If so, flush the pending code as a standalone code panel before replacing. Alternatively, accept the edge case: mid-execution view switches are extremely rare, and the `ai_exec_result` will still render (just as raw text in debug view, not as a grouped panel). The simpler approach is acceptable.
**Warning signs:** After switching views mid-AI-execution, the code panel is missing but the output panel appears.

### Pitfall 2: DebugView Showing Too Much for Markdown Channel

**What goes wrong:** The `ai` channel has `markdown=True`. In USER view, markdown renders via Rich Markdown. In DEBUG view, the raw markdown source is displayed. This is correct for debugging. But the raw markdown can be very long (full AI response), flooding the terminal.
**Why it happens:** DebugView shows raw content. AI responses are often 500+ characters of markdown.
**How to avoid:** This is actually the desired behavior for debug view -- showing raw data IS the point. But consider truncating very long content in DebugView with a `(... N chars total)` suffix at, say, 500 characters. This keeps debug view scannable without losing the metadata header.
**Warning signs:** Debug view producing walls of text that scroll past the visible terminal.

### Pitfall 3: Ctrl+V Collision with Quoted Insert

**What goes wrong:** prompt_toolkit's default key bindings include Ctrl+V as "quoted-insert" (insert next character literally). Adding `@kb.add("c-v")` overrides this.
**Why it happens:** prompt_toolkit processes custom key bindings before defaults.
**How to avoid:** This is acceptable because quoted-insert is rarely needed in this REPL. If it becomes a problem, use Ctrl+Shift+V or a different binding. The architecture research specifically recommended Ctrl+V as the view toggle mnemonic.
**Warning signs:** User cannot insert literal control characters via Ctrl+V followed by the character.

### Pitfall 4: Toolbar Style Class Not Defined

**What goes wrong:** The view widget uses `"class:toolbar.view"` style class, but the PromptSession Style dict in shell.py does not define it. The widget renders but with no styling (plain text).
**Why it happens:** New toolbar widgets need corresponding style entries in the Style.from_dict() call.
**How to avoid:** Add `"toolbar.view": "bg:#303030 #ffaf87"` (or similar) to the style dict in CortexShell.__init__() alongside existing toolbar styles.
**Warning signs:** View mode indicator appears unstyled in the toolbar.

### Pitfall 5: AISelfView Missing Prompt/Feedback Metadata

**What goes wrong:** The architecture research mentions AISelfView showing "prompts sent" and "feedback received" with metadata types `"prompt"`, `"feedback"`, `"context"`. But the current eval loop in ai.py does NOT write these metadata types. It writes `"response"` for AI output and `"[Output]\n..."` as the feedback TEXT, but the feedback text is not written to any channel -- it goes directly to `_send()`.
**Why it happens:** The eval loop was designed for execution, not observability. Feedback flows internally without touching channels.
**How to avoid:** AISelfView must work with the metadata types that ACTUALLY EXIST, not hypothetical ones. The existing types are: `response`, `ai_exec`, `ai_exec_result`, `tool_translated`, `tool_result`, `error`, `stdout`, `expr_result`, `warning`, `exec_notice`. AISelfView renders these with AI-perspective labeling (what this data means to the eval loop), not with new metadata types. Adding new channel writes for "prompt" and "feedback" would require modifying ai.py, which increases scope. Defer prompt/feedback channel writes to a future phase if needed.
**Warning signs:** AISelfView has render branches for metadata types that are never produced, making those branches dead code.

## Code Examples

### DebugView Implementation

```python
class DebugView:
    """Raw content with full metadata for debugging."""

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        meta_str = " ".join(f"{k}={v}" for k, v in sorted(meta.items()))
        header = f"[{channel_name}] {meta_str}" if meta_str else f"[{channel_name}]"
        print_formatted_text(FormattedText([(f"{color} bold", header)]))
        for line in content.splitlines():
            print_formatted_text(FormattedText([
                ("fg:#808080", "  "),
                ("", line),
            ]))
```

Source: Follows the existing prefix display pattern from channels.py:118-125, with metadata header added.

### AISelfView Implementation

```python
class AISelfView:
    """Shows channel data from the AI's perspective."""

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        content_type = meta.get("type", "")
        label = meta.get("label", "")

        # Tag map: what each metadata type means in the eval loop
        tag_map = {
            "response": "ai-output",
            "ai_exec": "exec-code",
            "ai_exec_result": "exec-result",
            "tool_translated": "tool-call",
            "tool_result": "tool-output",
            "error": "error",
        }
        tag = tag_map.get(content_type, content_type or channel_name)
        if label:
            tag = f"{tag}:{label}"

        print_formatted_text(FormattedText([
            ("fg:#b0b040 bold", f"[{tag}]"),
        ]))
        for line in content.splitlines():
            print_formatted_text(FormattedText([
                ("fg:#808080", "  "),
                ("", line),
            ]))
```

Source: Designed from metadata type analysis of ai.py and shell.py channel writes.

### ViewMode Enum and VIEW_FORMATTERS

```python
# In views.py
from enum import Enum

class ViewMode(Enum):
    USER = "user"
    DEBUG = "debug"
    AI_SELF = "ai-self"

VIEW_CYCLE = [ViewMode.USER, ViewMode.DEBUG, ViewMode.AI_SELF]

VIEW_FORMATTERS: dict[ViewMode, type] = {
    ViewMode.USER: UserView,
    ViewMode.DEBUG: DebugView,
    ViewMode.AI_SELF: AISelfView,
}
```

Source: Follows Mode enum pattern in modes.py.

### Shell Integration: _set_view and Keybinding

```python
# In CortexShell.__init__:
from bae.repl.views import UserView, ViewMode, VIEW_CYCLE, VIEW_FORMATTERS

self.view_mode = ViewMode.USER
# (existing) self.router.py._formatter = UserView()
# Change to: set all channels to USER view
self._set_view(ViewMode.USER)

# Method on CortexShell:
def _set_view(self, mode: ViewMode) -> None:
    """Switch all channels to the given view mode."""
    self.view_mode = mode
    formatter = VIEW_FORMATTERS[mode]()
    for ch in self.router._channels.values():
        ch._formatter = formatter

# In _build_key_bindings:
@kb.add("c-v")
def cycle_view(event):
    """Ctrl+V cycles view modes."""
    idx = VIEW_CYCLE.index(shell.view_mode)
    shell.view_mode = VIEW_CYCLE[(idx + 1) % len(VIEW_CYCLE)]
    shell._set_view(shell.view_mode)
    event.app.invalidate()
```

Source: Follows existing Shift+Tab mode cycling pattern in shell.py:117-122.

### Toolbar View Widget

```python
# In toolbar.py
def make_view_widget(shell) -> ToolbarWidget:
    """Built-in widget: active view mode (hidden in default user view)."""
    def widget():
        if shell.view_mode.value == "user":
            return []
        return [("class:toolbar.view", f" {shell.view_mode.value} ")]
    return widget
```

Source: Follows make_mode_widget pattern in toolbar.py:69-73.

### Test: DebugView Shows Metadata

```python
@patch("bae.repl.views.print_formatted_text")
def test_debug_view_shows_metadata(mock_pft):
    """DebugView renders metadata fields in header."""
    view = DebugView()
    view.render("py", "#87ff87", "x = 42", metadata={"type": "ai_exec", "label": "1"})
    # First call is the header with metadata
    header_arg = mock_pft.call_args_list[0][0][0]
    header_text = list(header_arg)[0][1]  # (style, text) tuple
    assert "label=1" in header_text
    assert "type=ai_exec" in header_text
```

### Test: View Mode Cycling

```python
def test_view_mode_cycle():
    """VIEW_CYCLE contains all three modes in order."""
    assert VIEW_CYCLE == [ViewMode.USER, ViewMode.DEBUG, ViewMode.AI_SELF]

def test_view_formatters_maps_all_modes():
    """Every ViewMode has a formatter class."""
    for mode in ViewMode:
        assert mode in VIEW_FORMATTERS
```

### Test: _set_view Updates All Channels

```python
def test_set_view_updates_all_channels():
    """_set_view sets formatter on every registered channel."""
    shell = CortexShell()
    shell._set_view(ViewMode.DEBUG)
    for ch in shell.router._channels.values():
        assert isinstance(ch._formatter, DebugView)
```

## Metadata Type Inventory

Complete inventory of metadata types written to channels (determines what DebugView and AISelfView must handle):

| Channel | Metadata Type | Source | Description |
|---------|--------------|--------|-------------|
| `ai` | `response` | ai.py eval loop | AI response text (with `label`) |
| `ai` | `error` | shell.py NL handler | Traceback from AI call failure |
| `py` | `ai_exec` | ai.py eval loop | Code the AI is executing (with `label`) |
| `py` | `ai_exec_result` | ai.py eval loop | Execution output (with `label`) |
| `py` | `tool_translated` | ai.py eval loop | Tool call tag that was translated (with `label`) |
| `py` | `tool_result` | ai.py eval loop | Tool call output (with `label`) |
| `py` | `stdout` | shell.py PY dispatch | Captured stdout from user code |
| `py` | `expr_result` | shell.py PY dispatch | Expression result repr |
| `py` | `warning` | shell.py PY dispatch | Unawaited coroutine warning |
| `py` | `error` | shell.py PY dispatch | Traceback |
| `bash` | `error` | shell.py BASH dispatch | Traceback |
| `bash` | `stderr` | shell.py BASH dispatch | stderr output |
| `graph` | `error` | shell.py GRAPH dispatch | Traceback |
| `graph` | `log` | shell.py channel_arun | Graph execution log |
| `graph` | `result` | shell.py channel_arun | Terminal node result |
| `debug` | `exec_notice` | ai.py eval loop | Multi-block exec notice (with `label`) |
| `debug` | (none) | shell.py various | Debug messages (cancelled task, etc.) |
| `repl` | (none) | shell.py run() | User input (direction=input, no metadata type) |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single display path per channel | ViewFormatter protocol with delegation | Phase 23 | Enables pluggable display |
| Flat `[py]` prefix for AI exec | Rich Panel with Syntax highlighting | Phase 24 | AI execution visually distinct |
| No view switching | Ctrl+V view toggle with ViewMode enum | Phase 25 (this phase) | User controls display at runtime |
| No debug visibility into metadata | DebugView with metadata header | Phase 25 (this phase) | Full pipeline transparency |

**Deprecated/outdated:**
- Nothing deprecated. Phase 25 adds new formatters and a toggle mechanism. UserView remains the default view.

## Open Questions

1. **Should _set_view set the SAME formatter instance on all channels, or separate instances per channel?**
   - What we know: UserView has buffer state (`_pending_code`). If one formatter instance is shared across channels, `ai` channel writes could theoretically interfere with `py` channel buffer state. But UserView only buffers `ai_exec` and `ai_exec_result`, which only come through the `py` channel.
   - What's unclear: Whether future formatters might have per-channel state.
   - Recommendation: Use ONE shared instance per view switch. UserView's buffer state is only triggered by `py` channel metadata types. A shared instance is simpler and more memory efficient. If per-channel state becomes needed, switch to per-channel instances later.

2. **Should DebugView truncate long content?**
   - What we know: AI responses can be 500+ characters. In debug view, showing the full response floods the terminal.
   - What's unclear: Whether truncation would hide useful debug information.
   - Recommendation: Show full content for now. If UAT reveals usability issues, add optional truncation with a `(... N chars)` suffix. Truncation is easy to add later; premature truncation hides bugs.

3. **Should AISelfView add new channel writes for prompt/feedback visibility?**
   - What we know: The eval loop sends feedback to `_send()` without writing to any channel. The "AI self view" concept from the architecture research envisions showing what prompts and feedback the AI receives.
   - What's unclear: Whether adding new channel writes to ai.py is in scope for Phase 25.
   - Recommendation: Defer. AISelfView works with existing metadata types. Adding prompt/feedback channel writes is a separate concern (observability) that increases scope. AISelfView already provides value by re-labeling existing writes from the AI's perspective.

4. **Should RawView be included?**
   - What we know: The architecture research mentions RawView (no formatting at all). The REQUIREMENTS.md does not list it. The success criteria mention three views: debug, AI-self, and user.
   - Recommendation: Do not include RawView. Three views (USER, DEBUG, AI_SELF) satisfy the requirements. YAGNI.

## Sources

### Primary (HIGH confidence)
- `bae/repl/views.py` -- UserView implementation, `_rich_to_ansi()` helper (direct codebase reading)
- `bae/repl/channels.py` -- ViewFormatter protocol, Channel._formatter field, `_display()` delegation (direct codebase reading)
- `bae/repl/shell.py` -- CortexShell, `_build_key_bindings()`, toolbar setup, UserView wiring (direct codebase reading)
- `bae/repl/toolbar.py` -- ToolbarConfig, make_mode_widget pattern (direct codebase reading)
- `bae/repl/modes.py` -- Mode enum, MODE_CYCLE pattern (direct codebase reading)
- `bae/repl/ai.py` -- Eval loop metadata types, channel writes (direct codebase reading)
- `bae/repl/shell.py` -- All channel metadata types from dispatch methods (direct codebase reading)
- `tests/repl/test_views.py` -- 10 existing UserView tests (direct codebase reading)
- `tests/repl/test_channels.py` -- 45 existing tests including ViewFormatter delegation (direct codebase reading)
- `.planning/phases/23-view-framework/23-RESEARCH.md` -- ViewFormatter protocol design rationale
- `.planning/phases/24-execution-display/24-RESEARCH.md` -- UserView patterns, Rich-to-ANSI bridge
- `.planning/research/ARCHITECTURE.md` -- View mode switching design, DebugView concept, AISelfView concept
- `.planning/research/PITFALLS.md` -- Pitfalls 8 (patch_stdout bypass), 10 (debug toggle global state)
- `.planning/research/FEATURES.md` -- Feature landscape, anti-features, view registry design

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` -- VIEW-04, VIEW-05, VIEW-06 definitions
- `.planning/ROADMAP.md` -- Phase 25 success criteria

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all imports already in the codebase
- Architecture: HIGH -- all patterns proven by UserView (Phase 24), all infrastructure exists (Phase 23), keybinding and toolbar patterns well-established in shell.py
- Pitfalls: HIGH -- pitfalls identified from direct codebase analysis, most are edge cases (mid-execution view switch) rather than fundamental design risks

**Research date:** 2026-02-14
**Valid until:** Indefinite -- internal architecture over stable Rich 14.x and prompt_toolkit 3.x. No external version sensitivity.
