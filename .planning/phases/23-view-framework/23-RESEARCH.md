# Phase 23: View Framework - Research

**Researched:** 2026-02-14
**Domain:** Pluggable display strategy for Channel output in a prompt_toolkit + Rich REPL
**Confidence:** HIGH

## Summary

Phase 23 is a surgical refactor of `Channel._display()` to support a pluggable formatter strategy. The scope is narrow: define a `ViewFormatter` protocol, add a `_formatter` field to `Channel`, and modify `_display()` to delegate when a formatter is set while preserving the exact existing behavior when unset.

No new dependencies are needed. The existing codebase already has the `@runtime_checkable` Protocol pattern in `bae/lm.py` (`LM` protocol, line 271) and the Rich-to-prompt_toolkit ANSI bridge in `channels.py` (`render_markdown()`, line 30). Phase 23 adds the protocol and the delegation hook -- it does NOT create any concrete view implementations (those are Phase 24 and 25).

The critical constraint is zero regression: all 39 existing channel tests must pass without modification after the formatter infrastructure is added. The default path (no formatter set) must execute the exact same `_display()` code that exists today.

**Primary recommendation:** Add `ViewFormatter` protocol to `channels.py` (not a new file), add `_formatter: ViewFormatter | None = None` to `Channel` dataclass, and modify `_display()` with a single conditional delegation. Keep the change minimal -- this is infrastructure, not features.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `typing.Protocol` | stdlib (3.14) | Structural typing for formatter interface | Already used in codebase (`LM` protocol in `bae/lm.py`) |
| `typing.runtime_checkable` | stdlib (3.14) | Enables `isinstance()` checks against protocol | Already used in codebase (`LM` protocol) |
| `rich` | 14.3.2 (installed) | Terminal rendering (Panel, Syntax, Markdown) | Already the rendering engine for markdown channels |
| `prompt_toolkit` | 3.0.52 (installed) | REPL framework, ANSI display | Already the REPL shell framework |

### Supporting

No additional libraries needed. Phase 23 uses only what is already installed and imported.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `Protocol` | `ABC` with `abstractmethod` | ABC forces inheritance. Protocol allows structural typing -- any object with the right `render()` method works. Protocol matches the existing codebase convention (LM). |
| `Protocol` | Plain callable `Callable[[str, str, str, dict], None]` | Callable works for a single method, but is harder to document, extend with optional methods, and type-check meaningfully. Protocol is more explicit. |
| Formatter on Channel | Formatter on ChannelRouter | Router-level formatting would mean all channels share one formatter. Per-channel formatter gives finer control (Phase 25 may want different formatters per channel). The architecture docs recommend per-channel. |

**Installation:** None. Zero new dependencies.

## Architecture Patterns

### Recommended Structure

Phase 23 changes are confined to a single file:

```
bae/repl/
  channels.py     MODIFIED  -- ViewFormatter protocol + Channel._formatter + _display delegation
```

No new files. No changes to other modules. The protocol and the delegation live together in `channels.py` because that is where `Channel` and `_display()` live. Creating a separate `views.py` at this stage would be premature -- that file is for Phase 24/25 when concrete formatters exist.

### Pattern: Strategy via Protocol (Formatter as Strategy)

**What:** `ViewFormatter` is the Strategy pattern. Channel delegates display to a swappable formatter object.
**When:** `_display()` is called and `self._formatter is not None`.
**Why not subclass Channel:** Channels do not change type. A Channel named "ai" is always "ai" -- only its display behavior changes. Subclassing would require replacing Channel objects, breaking references held by router, store, and namespace.

```python
# Source: bae/lm.py existing LM protocol pattern
@runtime_checkable
class ViewFormatter(Protocol):
    """Display strategy for channel content."""

    def render(
        self,
        channel_name: str,
        color: str,
        content: str,
        *,
        metadata: dict | None = None,
    ) -> None:
        """Format and display content from a channel write."""
        ...
```

**Integration in Channel._display():**

```python
def _display(self, content: str, *, metadata: dict | None = None) -> None:
    if self._formatter is not None:
        self._formatter.render(self.name, self.color, content, metadata=metadata)
        return
    # Existing display logic (unchanged) follows below
    ...
```

### Pattern: Rich-to-ANSI Bridge (Existing, Reused)

**What:** All Rich rendering goes through `Console(file=StringIO(), force_terminal=True)` then `print_formatted_text(ANSI(...))`.
**When:** Every formatter that uses Rich renderables (Phase 24/25).
**Why:** prompt_toolkit's `patch_stdout` requires all terminal output to go through prompt_toolkit's rendering pipeline. Direct `Console.print()` to stdout corrupts the prompt.
**Source:** `channels.py:30-40` (`render_markdown()`) -- already in production.

This pattern is NOT needed in Phase 23 (no concrete formatters), but the protocol's render() method signature is designed to support it. Formatters call `print_formatted_text()` internally.

### Pattern: Metadata-Driven Rendering

**What:** Formatters decide how to render based on `metadata["type"]`, not by parsing content.
**When:** Concrete formatters (Phase 24/25) choose between panel styles, grouping, formatting.
**Why:** Parsing content is fragile and duplicates work. The producer (eval loop, shell) already knows what kind of content it is producing. Passing that knowledge via metadata is clean and testable.
**Source:** Already in use -- `ai.py:118` passes `metadata={"type": "response", "label": self._label}`.

Phase 23 ensures the metadata is passed through to the formatter via the `render()` signature. The existing `_display()` method already receives and uses metadata (for labels, lines 84-85).

### Anti-Patterns to Avoid

- **Channel Subclasses for Views:** Do not create `class AIChannel(Channel)`, `class DebugChannel(Channel)`. The router holds Channel references. Swapping subclasses at runtime means replacing objects, breaking external references.
- **View Formatter Modifying Content:** Formatters must render content as-is. Visual framing (panels, colors, syntax highlighting) is additive, not transformative. The content string is immutable through the pipeline. The stored version and displayed version must not diverge.
- **Rich Console Singleton:** Do not share a single Console object across render calls. Create a fresh `Console(file=StringIO())` per render. Rich Console carries state (cursor position, line count, style stack). Concurrent renders from background tasks would corrupt state.
- **Formatter on ChannelRouter (global):** Do not put a single formatter on the router that applies to all channels. Per-channel formatters allow fine-grained control. Phase 25 needs this when different channels have different formatting needs.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structural typing interface | Custom registration/duck-typing check | `typing.Protocol` with `@runtime_checkable` | Stdlib, IDE support, type-checker friendly. Already used for `LM` in this codebase. |
| Rich-to-terminal bridge | Manual ANSI escape code generation | `Console(file=StringIO()) + print_formatted_text(ANSI(...))` | Already proven in `render_markdown()`. All edge cases handled. |

**Key insight:** Phase 23 adds almost no new code. The value is in the *seam* -- the delegation point where `_display()` can optionally hand off to a formatter. The actual formatting logic comes in Phase 24/25.

## Common Pitfalls

### Pitfall 1: Breaking Existing Channel Display

**What goes wrong:** Introducing the formatter field or modifying `_display()` changes the behavior for channels without a formatter set. Tests mock `print_formatted_text` and check specific call patterns -- a new code path or changed calling convention breaks them.
**Why it happens:** The existing `_display()` method has two paths: markdown (2 calls to `print_formatted_text`) and non-markdown (N calls, one per line). Tests verify these exact call counts and argument shapes. If the delegation code introduces a different code path even when `_formatter is None`, the tests break.
**How to avoid:**
1. The `if self._formatter is not None:` check must be the FIRST line of `_display()`, returning early after delegation.
2. The `else` branch must be the EXACT existing code, unchanged -- not refactored, not cleaned up, not even reformatted.
3. Run `uv run python -m pytest tests/repl/test_channels.py -q` after every change. All 39 tests must pass.
**Warning signs:** Any test failure in `test_channels.py` after the change.

### Pitfall 2: Formatter Field Breaks Channel Dataclass

**What goes wrong:** Adding `_formatter` to the Channel dataclass changes its `__init__` signature, repr, or equality comparison. Existing code that constructs Channel objects (tests, router.register) breaks because of the new parameter.
**Why it happens:** Python dataclasses include all fields in `__init__` by default. If `_formatter` is not `field(default=None, repr=False)`, it changes Channel construction and repr output.
**How to avoid:** Use `_formatter: ViewFormatter | None = field(default=None, repr=False)` -- exactly matching the existing `_buffer` pattern (line 52: `_buffer: list[str] = field(default_factory=list, repr=False)`). The underscore prefix and `repr=False` keep it out of the public interface.
**Warning signs:** `test_channel_repr` tests failing, or `ChannelRouter.register()` raising TypeError.

### Pitfall 3: Protocol Import Causes Circular Dependencies

**What goes wrong:** If `ViewFormatter` is defined in a new `views.py` file and `channels.py` imports it, a circular dependency may arise when concrete formatters in `views.py` import Channel or ChannelRouter from `channels.py`.
**Why it happens:** Protocol definitions need to be importable by both the consumer (Channel) and the implementer (concrete formatters). Putting the protocol in the same file as the consumer avoids one direction of import.
**How to avoid:** Define `ViewFormatter` in `channels.py` alongside `Channel`. Concrete formatters (Phase 24/25) import `ViewFormatter` from `channels.py` and implement it. No circular import possible because the flow is one-directional: `views.py` imports from `channels.py`, never the reverse.
**Warning signs:** `ImportError` at import time.

### Pitfall 4: Formatter Bypasses prompt_toolkit patch_stdout

**What goes wrong:** A concrete formatter creates a Rich Console writing to `sys.stdout` directly instead of StringIO, bypassing `patch_stdout()` and corrupting the prompt display.
**Why it happens:** Every Rich tutorial starts with `console = Console()` which writes to stdout.
**How to avoid:** Phase 23 only defines the protocol -- no concrete formatters to make this mistake. But the protocol docstring and architecture docs should warn implementers. Phase 24/25 research should emphasize this.
**Warning signs:** Characters appearing inside the input area, cursor jumping during AI output.

## Code Examples

### ViewFormatter Protocol Definition

```python
# In channels.py, after existing imports
from typing import Protocol, runtime_checkable

@runtime_checkable
class ViewFormatter(Protocol):
    """Display strategy for channel content.

    Receives channel name, color, content, and optional metadata.
    Renders to terminal via print_formatted_text (prompt_toolkit).
    All Rich rendering MUST use Console(file=StringIO()) -- never stdout directly.
    """

    def render(
        self,
        channel_name: str,
        color: str,
        content: str,
        *,
        metadata: dict | None = None,
    ) -> None:
        """Format and display content from a channel write."""
        ...
```

Source: Matches existing `LM` protocol pattern in `bae/lm.py:271-314`.

### Channel Dataclass Modification

```python
@dataclass
class Channel:
    """A labeled output stream with color-coded display and store integration."""

    name: str
    color: str
    visible: bool = True
    markdown: bool = False
    store: SessionStore | None = None
    _formatter: ViewFormatter | None = field(default=None, repr=False)
    _buffer: list[str] = field(default_factory=list, repr=False)
```

Source: Follows existing `_buffer` pattern at `channels.py:52`.

### Modified _display() Method

```python
def _display(self, content: str, *, metadata: dict | None = None) -> None:
    """Render content to terminal, delegating to formatter when set.

    When a formatter is set, it receives channel name, color, content, and
    metadata for custom rendering. When no formatter is set, the existing
    color-coded prefix display runs unchanged.
    """
    if self._formatter is not None:
        self._formatter.render(self.name, self.color, content, metadata=metadata)
        return

    # Existing display logic (unchanged from here down)
    label_text = self.label
    if metadata and "label" in metadata:
        label_text = f"[{self.name}:{metadata['label']}]"

    if self.markdown:
        label = FormattedText([(f"{self.color} bold", label_text)])
        print_formatted_text(label)
        ansi_text = render_markdown(content)
        print_formatted_text(ANSI(ansi_text))
    else:
        for line in content.splitlines():
            text = FormattedText([
                (f"{self.color} bold", label_text),
                ("", " "),
                ("", line),
            ])
            print_formatted_text(text)
```

Source: Existing `_display()` at `channels.py:76-99`, with delegation prepended.

### Test: Formatter Receives Correct Arguments

```python
def test_channel_display_delegates_to_formatter():
    """When _formatter is set, _display() delegates to formatter.render()."""
    mock_formatter = MagicMock()
    ch = Channel(name="py", color="#87ff87")
    ch._formatter = mock_formatter
    ch._display("hello", metadata={"type": "test"})
    mock_formatter.render.assert_called_once_with(
        "py", "#87ff87", "hello", metadata={"type": "test"}
    )
```

### Test: No Formatter Falls Back to Existing Behavior

```python
@patch("bae.repl.channels.print_formatted_text")
def test_channel_display_no_formatter_unchanged(mock_pft):
    """When _formatter is None, _display() uses existing line-by-line rendering."""
    ch = Channel(name="py", color="#87ff87")
    ch._display("x = 42")
    mock_pft.assert_called_once()
    fragments = list(mock_pft.call_args[0][0])
    assert fragments[0] == ("#87ff87 bold", "[py]")
    assert fragments[2] == ("", "x = 42")
```

### Test: ViewFormatter Protocol Shape

```python
def test_view_formatter_protocol_shape():
    """ViewFormatter protocol requires render() with correct signature."""
    class GoodFormatter:
        def render(self, channel_name, color, content, *, metadata=None):
            pass

    class BadFormatter:
        def render(self, content):  # wrong signature
            pass

    assert isinstance(GoodFormatter(), ViewFormatter)
    # Note: runtime_checkable only checks method existence, not signature
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Direct `_display()` in Channel | Strategy pattern with formatter delegation | Phase 23 (this phase) | Enables pluggable display without modifying Channel identity |
| Single display path | Dual path: formatter or fallback | Phase 23 | Zero-cost abstraction when formatter is None |

**Deprecated/outdated:**
- Nothing deprecated. Phase 23 adds a new code path; the old path is preserved exactly.

## Open Questions

1. **Should ChannelRouter.register() accept a formatter parameter?**
   - What we know: Currently `register()` takes name, color, store, markdown. Adding formatter would let channels be created with a formatter from the start.
   - What's unclear: Phase 24/25 may want to set formatters dynamically (e.g., when user toggles view mode). Baking it into register() may be premature.
   - Recommendation: Defer. Phase 23 only adds the `_formatter` field to Channel. Setting it happens externally (direct attribute access or a setter method). Phase 24/25 can add register() parameters if needed.

2. **Should `write()` pass metadata to the formatter, or should `_display()` do it?**
   - What we know: Currently `write()` calls `_display(content, metadata=metadata)`. The formatter needs metadata.
   - What's unclear: Nothing -- the existing `_display()` signature already receives metadata.
   - Recommendation: No change needed. `_display()` already receives metadata and passes it through to the formatter. The data flow is: `write() -> _display(content, metadata=metadata) -> formatter.render(..., metadata=metadata)`.

3. **Should the `markdown` flag on Channel interact with the formatter?**
   - What we know: When `_formatter is not None`, the formatter handles ALL rendering. The `markdown` flag is only used by the fallback `_display()` logic.
   - What's unclear: Should the formatter know whether the channel is markdown? The metadata could carry this, or the formatter could check `channel.markdown`.
   - Recommendation: Pass the `markdown` flag as context only if concrete formatters need it (Phase 24). For Phase 23, the formatter receives channel_name and color -- that is sufficient for the protocol. The `markdown` boolean is an implementation detail of the fallback display path.

## Sources

### Primary (HIGH confidence)
- `bae/repl/channels.py` -- Channel class, `_display()` method, `render_markdown()`, ChannelRouter -- direct codebase reading
- `bae/lm.py:271-314` -- Existing `@runtime_checkable` Protocol pattern (`LM` protocol) -- direct codebase reading
- `tests/repl/test_channels.py` -- 39 existing tests verifying Channel behavior -- direct codebase reading
- `.planning/research/ARCHITECTURE.md` -- v5.0 architecture research, ViewFormatter protocol design
- `.planning/research/PITFALLS.md` -- Pitfalls 1, 3, 8, 10 relevant to view framework
- `.planning/research/FEATURES.md` -- Feature landscape and dependency graph
- `.planning/research/STACK.md` -- Stack verification (no new deps needed)

### Secondary (MEDIUM confidence)
- `.planning/ROADMAP.md` -- Phase 23-25 success criteria and dependency chain
- `.planning/REQUIREMENTS.md` -- VIEW-01, VIEW-02 requirement definitions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, uses only existing stdlib and installed packages
- Architecture: HIGH -- Strategy pattern via Protocol is well-understood, matches existing codebase convention (LM protocol), and the integration point is a single method
- Pitfalls: HIGH -- all pitfalls identified from direct codebase analysis and existing research documents

**Research date:** 2026-02-14
**Valid until:** Indefinite -- this is internal architecture over stable stdlib. No external version sensitivity.
