# Architecture: v5.0 Multi-View Stream Framework

**Domain:** Multi-view display, tool call interception, execution framing for async REPL
**Researched:** 2026-02-14
**Confidence:** HIGH (direct codebase analysis + verified Rich Panel/Syntax API + existing rendering patterns)

## Existing Architecture (What v5.0 Extends)

### Current Display Pipeline

```
AI.__call__()
  |
  +-- _send(prompt) --> Claude CLI subprocess --> raw text response
  |
  +-- router.write("ai", response, metadata={"type": "response", "label": "1"})
  |     |
  |     +-- Channel.write()
  |           +-- store.record(...)
  |           +-- _buffer.append(content)
  |           +-- if visible: _display(content, metadata)
  |                 |
  |                 +-- [markdown=True]:  print label, then render_markdown() -> ANSI
  |                 +-- [markdown=False]: line-by-line with color-coded prefix
  |
  +-- extract_code(response) --> list[str] of code blocks
  |
  +-- for code in blocks:
  |     +-- async_exec(code, namespace) --> (result, captured)
  |     +-- router.write("py", code, metadata={"type": "ai_exec"})
  |     +-- router.write("py", output, metadata={"type": "ai_exec_result"})
  |
  +-- feedback = join(results) --> loop back to _send()
```

### Current Component Map (Relevant to v5.0)

| Component | Location | Role in v5.0 |
|-----------|----------|-------------|
| `Channel._display()` | channels.py:76-99 | **Modified** -- dispatch to view formatters |
| `Channel.write()` | channels.py:59-74 | **Unchanged** -- record + buffer + conditional display |
| `ChannelRouter.write()` | channels.py:122-137 | **Unchanged** -- dispatch to channel |
| `render_markdown()` | channels.py:30-40 | **Extended** -- one formatter among many |
| `AI.__call__()` | ai.py:71-125 | **Modified** -- add tool call detection step |
| `AI.extract_code()` | ai.py:199-202 | **Unchanged** -- used by tool call detector |
| `ai_prompt.md` | ai_prompt.md | **Modified** -- prompt hardening |
| `CortexShell.__init__()` | shell.py:209-255 | **Modified** -- add view mode state |

### Key Constraint: prompt_toolkit + Rich Bridge

The codebase already uses the Rich-to-prompt_toolkit bridge pattern. `render_markdown()` captures Rich output to StringIO with `force_terminal=True`, then `print_formatted_text(ANSI(...))` renders it. All new formatters MUST use this same bridge. No direct `Console.print()` to stdout -- everything goes through prompt_toolkit for `patch_stdout` compatibility.

## v5.0 Component Architecture

### New and Modified Components

```
bae/repl/
  channels.py     MODIFIED  -- ViewFormatter protocol, _display dispatches to formatter
  views.py        NEW       -- Concrete view formatters (user, debug, raw, ai-self)
  ai.py           MODIFIED  -- tool call detection between _send() and extract_code()
  ai_prompt.md    MODIFIED  -- hardened prompt with tool call conventions
  shell.py        MODIFIED  -- view mode state, debug toggle keybinding
```

### Component Diagram

```
                        User Input
                            |
                            v
                     AI.__call__()
                            |
                  +---------+---------+
                  |                   |
              _send()            [eval loop]
                  |                   |
                  v                   v
          raw response        extract_code()
                  |                   |
                  v                   |
         detect_tools()    <--- NEW   |
          (classify response          |
           content blocks)            |
                  |                   |
                  v                   v
          router.write("ai", ...)   router.write("py", ...)
                  |                   |
                  v                   v
           Channel.write()     Channel.write()
                  |                   |
                  v                   v
           Channel._display()  Channel._display()
                  |                   |
                  v                   v
        active_formatter.render()   active_formatter.render()
           |         |                    |
           v         v                    v
      UserView   DebugView          UserView (panels)
      (panels)   (raw + meta)       (framed exec)
```

## Component Detail

### 1. ViewFormatter Protocol (channels.py)

A ViewFormatter transforms channel content + metadata into terminal output. The Channel holds a reference to the active formatter and delegates `_display()` to it.

**Why a protocol, not inheritance:** Formatters are swappable at runtime (debug toggle). A Channel does not change type -- its formatter changes. This is composition over inheritance.

```python
from typing import Protocol

class ViewFormatter(Protocol):
    """Renders channel content to terminal."""

    def render(
        self,
        channel_name: str,
        color: str,
        content: str,
        *,
        metadata: dict | None = None,
    ) -> None:
        """Format and display content."""
        ...
```

**Integration point:** `Channel._display()` becomes a one-liner that delegates to the formatter.

```python
# channels.py -- modified Channel._display()
def _display(self, content: str, *, metadata: dict | None = None) -> None:
    self._formatter.render(self.name, self.color, content, metadata=metadata)
```

**Channel gains a `_formatter` field:**

```python
@dataclass
class Channel:
    name: str
    color: str
    visible: bool = True
    markdown: bool = False
    store: SessionStore | None = None
    _formatter: ViewFormatter | None = field(default=None, repr=False)
    _buffer: list[str] = field(default_factory=list, repr=False)
```

When `_formatter is None`, the current `_display()` logic runs as-is (backward compatible). When set, it delegates entirely. This means v5.0 formatters are opt-in per channel -- you can set a formatter on the `ai` and `py` channels while leaving `bash`, `graph`, and `debug` on their current display path.

### 2. Concrete View Formatters (views.py -- NEW FILE)

Four formatters, one active at a time per channel. All use the Rich-to-prompt_toolkit bridge.

#### UserView (default)

The user-facing view. Uses Rich Panels for framed display of AI responses and execution blocks.

```python
class UserView:
    """Framed panels for user-facing display."""

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        content_type = meta.get("type", "")

        if content_type == "response":
            # AI response: framed panel with markdown rendering
            self._render_ai_response(channel_name, color, content, meta)
        elif content_type == "ai_exec":
            # Code the AI is executing: syntax-highlighted panel
            self._render_exec_code(channel_name, color, content, meta)
        elif content_type == "ai_exec_result":
            # Execution output: output panel
            self._render_exec_output(channel_name, color, content, meta)
        else:
            # Fallback: prefixed lines (current behavior)
            self._render_prefixed(channel_name, color, content, meta)
```

**AI response rendering (framed panel):**

```python
from rich.panel import Panel
from rich.markdown import Markdown
from rich import box

def _render_ai_response(self, channel_name, color, content, meta):
    label = meta.get("label", "")
    title = f"{channel_name}:{label}" if label else channel_name

    panel = Panel(
        Markdown(content),
        title=f"[bold]{title}[/]",
        border_style=color,
        box=box.ROUNDED,
        padding=(0, 1),
    )
    ansi = _rich_to_ansi(panel)
    print_formatted_text(ANSI(ansi))
```

**Execution code rendering (syntax-highlighted panel):**

```python
from rich.syntax import Syntax

def _render_exec_code(self, channel_name, color, content, meta):
    label = meta.get("label", "")
    title = f"{channel_name}:{label}" if label else channel_name

    panel = Panel(
        Syntax(content, "python", theme="monokai"),
        title=f"[bold]{title}[/]",
        subtitle="[dim]exec[/]",
        border_style="dim",
        box=box.ROUNDED,
        padding=(0, 1),
    )
    ansi = _rich_to_ansi(panel)
    print_formatted_text(ANSI(ansi))
```

**Execution output rendering:**

```python
def _render_exec_output(self, channel_name, color, content, meta):
    label = meta.get("label", "")
    title = f"{channel_name}:{label}" if label else channel_name

    panel = Panel(
        content,
        title=f"[bold]{title}[/]",
        subtitle="[dim]output[/]",
        border_style="dim green" if "Error" not in content else "dim red",
        box=box.ROUNDED,
        padding=(0, 1),
    )
    ansi = _rich_to_ansi(panel)
    print_formatted_text(ANSI(ansi))
```

#### DebugView

Shows raw content with full metadata. Used during development or when debugging AI behavior.

```python
class DebugView:
    """Raw content with metadata for debugging."""

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        # Header with all metadata
        header = f"[{channel_name}] type={meta.get('type','?')} label={meta.get('label','?')}"
        _print_prefixed(header, color)
        # Raw content, no markdown rendering
        for line in content.splitlines():
            _print_prefixed(f"  {line}", "#808080")
```

#### RawView

No formatting at all. Content as-is. Useful for piping or copy-paste.

```python
class RawView:
    """Unformatted content output."""

    def render(self, channel_name, color, content, *, metadata=None):
        print_formatted_text(FormattedText([("", content)]))
```

#### AISelfView

What the AI "sees" -- shows the prompts, feedback, context injections. Renders the content the AI receives, not what it produces.

```python
class AISelfView:
    """Shows AI perspective: prompts sent, feedback received."""

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        content_type = meta.get("type", "")

        if content_type in ("prompt", "feedback", "context"):
            panel = Panel(
                content,
                title=f"[dim]{content_type}[/]",
                border_style="dim yellow",
                box=box.SIMPLE,
                padding=(0, 1),
            )
            ansi = _rich_to_ansi(panel)
            print_formatted_text(ANSI(ansi))
        else:
            # Non-prompt content is dimmed
            _print_prefixed(content, "#555555")
```

**Note:** AISelfView requires new metadata types (`"prompt"`, `"feedback"`, `"context"`) to be emitted by `AI.__call__()`. This is part of the AI modifications.

#### Shared Helper

```python
def _rich_to_ansi(renderable) -> str:
    """Render any Rich renderable to ANSI string for prompt_toolkit."""
    buf = StringIO()
    console = Console(
        file=buf,
        width=os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 80,
        force_terminal=True,
    )
    console.print(renderable)
    return buf.getvalue()
```

This is an extracted generalization of the existing `render_markdown()` function in channels.py. The existing function remains as a convenience but can internally call `_rich_to_ansi(Markdown(text, ...))`.

### 3. Tool Call Detection (ai.py -- MODIFIED)

**Where in the eval loop:** Between `_send()` response and `extract_code()`.

Currently the eval loop is:
```
response = _send(prompt)
router.write("ai", response)
blocks = extract_code(response)
```

v5.0 adds a classification step:
```
response = _send(prompt)
classified = classify_response(response)  # NEW
router.write("ai", classified.text, metadata={..., "tools": classified.tools})
blocks = extract_code(response)  # unchanged -- still extracts code
```

**What `classify_response` does:**

It does NOT change the response content. It annotates what kinds of "tool calls" the AI is making. In cortex, "tool calls" are not API tool_use blocks (those are disabled via `--tools ""`). They are patterns in the AI's text response:

| Pattern | Tool Type | Detection |
|---------|-----------|-----------|
| ` ```python ... ``` ` | `code_exec` | Existing `extract_code()` regex |
| `ns()` or `ns(obj)` | `inspect` | Substring match in code blocks |
| `store.search(...)` | `store_query` | Substring match in code blocks |
| `import ...` | `import` | AST parse of code blocks |
| Prose-only response | `none` | No code blocks found |

```python
@dataclass
class ResponseClassification:
    """What kinds of tool calls the AI response contains."""
    text: str                    # Original response text
    tools: list[str]             # e.g. ["code_exec", "inspect"]
    code_blocks: list[str]       # Extracted code (same as extract_code)
    has_code: bool               # Convenience: len(code_blocks) > 0


def classify_response(text: str) -> ResponseClassification:
    """Classify the tool calls in an AI response."""
    blocks = AI.extract_code(text)
    tools = []

    if blocks:
        tools.append("code_exec")
        combined = "\n".join(blocks)
        if "ns(" in combined:
            tools.append("inspect")
        if "store." in combined:
            tools.append("store_query")
        # AST-based import detection
        for block in blocks:
            try:
                tree = ast.parse(block)
                if any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree)):
                    tools.append("import")
                    break
            except SyntaxError:
                pass

    return ResponseClassification(
        text=text,
        tools=tools,
        code_blocks=blocks,
        has_code=bool(blocks),
    )
```

**Why classify before display:** The view formatter uses the tool classification to decide how to render. UserView shows a code panel for `code_exec`, a special "inspecting..." indicator for `inspect`. DebugView shows the raw tool list. Without classification, the formatter would have to re-parse the content.

**Integration with eval loop:**

```python
async def __call__(self, prompt: str) -> str:
    # ... existing context building ...
    response = await self._send(full_prompt)
    await asyncio.sleep(0)

    classified = classify_response(response)

    self._router.write("ai", response, mode="NL", metadata={
        "type": "response",
        "label": self._label,
        "tools": classified.tools,      # NEW
    })

    for _ in range(self._max_eval_iters):
        if not classified.has_code:
            break

        results = []
        for code in classified.code_blocks:
            # ... existing execution logic (unchanged) ...
            pass

        feedback = "\n".join(...)
        await asyncio.sleep(0)
        response = await self._send(feedback)
        await asyncio.sleep(0)

        classified = classify_response(response)   # Re-classify each iteration

        self._router.write("ai", response, mode="NL", metadata={
            "type": "response",
            "label": self._label,
            "tools": classified.tools,
        })

    return response
```

**Key design decision:** `classify_response` is a pure function, not a method on AI. It takes text, returns a dataclass. No side effects, no state, fully testable in isolation.

### 4. Execution Display Framing (views.py -- UserView)

The current display for AI code execution is prefixed lines:

```
[py] x = 42
[py] print(x)
[py] 42
```

v5.0 replaces this with framed Rich Panels:

```
 ai:1 exec
 x = 42           <- syntax highlighted
 print(x)
 output
 42
```

**Implementation:** The UserView formatter handles `ai_exec` and `ai_exec_result` metadata types with Panel rendering (shown in UserView section above).

**Grouped execution display (code + output in one panel):**

For the most polished experience, code and output can be grouped into a single panel using Rich's `Group` renderable:

```python
from rich.console import Group
from rich.rule import Rule

def _render_exec_grouped(self, code: str, output: str, meta: dict):
    """Render code + output as a single framed panel."""
    label = meta.get("label", "")
    title = f"ai:{label}" if label else "ai"

    parts = [Syntax(code, "python", theme="monokai")]
    if output:
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
```

**Challenge:** The eval loop writes code and output as separate `router.write()` calls. To group them, the formatter needs to buffer the `ai_exec` write and wait for the corresponding `ai_exec_result` before rendering both.

**Solution -- buffered exec display:**

```python
class UserView:
    def __init__(self):
        self._pending_exec: str | None = None
        self._pending_meta: dict | None = None

    def render(self, channel_name, color, content, *, metadata=None):
        meta = metadata or {}
        content_type = meta.get("type", "")

        if content_type == "ai_exec":
            # Buffer the code, wait for output
            self._pending_exec = content
            self._pending_meta = meta
            return

        if content_type == "ai_exec_result" and self._pending_exec is not None:
            # Render grouped code + output
            self._render_exec_grouped(self._pending_exec, content, self._pending_meta)
            self._pending_exec = None
            self._pending_meta = None
            return

        # ... other content types ...
```

This is safe because the eval loop always writes `ai_exec` immediately followed by `ai_exec_result` for the same block, synchronously within the same coroutine. No interleaving is possible.

### 5. View Mode Switching (shell.py -- MODIFIED)

**State:** `CortexShell` gains a `view_mode` field and a keybinding to cycle views.

```python
class ViewMode(Enum):
    USER = "user"
    DEBUG = "debug"
    RAW = "raw"
    AI_SELF = "ai_self"

VIEW_CYCLE = [ViewMode.USER, ViewMode.DEBUG, ViewMode.RAW, ViewMode.AI_SELF]
```

**Keybinding:** Ctrl+V cycles view modes (mnemonic: View). On cycle, update the formatter on each channel.

```python
@kb.add("c-v")
def cycle_view(event):
    idx = VIEW_CYCLE.index(shell.view_mode)
    shell.view_mode = VIEW_CYCLE[(idx + 1) % len(VIEW_CYCLE)]
    formatter = VIEW_FORMATTERS[shell.view_mode]
    for ch in shell.router._channels.values():
        ch._formatter = formatter
    shell.router.write("debug", f"view: {shell.view_mode.value}", mode="DEBUG")
    event.app.invalidate()
```

**Toolbar indicator:** Add a view widget showing current view mode:

```python
def make_view_widget(shell) -> ToolbarWidget:
    return lambda: [("class:toolbar.view", f" {shell.view_mode.value} ")]
```

### 6. AI Prompt Hardening (ai_prompt.md -- MODIFIED)

The current prompt is 68 lines. v5.0 adds structured tool call conventions so the AI's responses are consistently parseable.

**Key additions:**

```markdown
## Tool Conventions
- Code blocks are your tools. Every fence is executed immediately.
- Use EXACTLY ONE code fence per response when you need to act.
- If you need multiple steps, let the eval loop iterate -- do not put multiple fences.
- NEVER produce code you do not want executed.
- NEVER produce code that calls ai() or ai.fill() -- you ARE the ai.

## Response Structure
When responding with code:
1. Brief explanation of what you are doing (1-2 sentences)
2. Single code fence
3. No text after the fence (wait for execution result)

When responding without code:
- Answer directly in prose
- Do NOT wrap answers in code blocks
```

**Why 1-fence-per-response:** The current eval loop handles multiple code blocks per response, but this creates ambiguity about which block produced which output. The AI gets cleaner feedback when it runs one block, sees the result, then decides the next action. The `max_eval_iters` limit ensures convergence.

**Confidence:** MEDIUM. Prompt changes require empirical testing. The structure is sound but the exact wording needs iteration based on observed AI behavior.

## Data Flow (v5.0)

### AI Response Flow (Modified)

```
AI._send(prompt)
     |
     v
  raw text response
     |
     v
  classify_response(response)  ------> ResponseClassification
     |                                    .text
     |                                    .tools = ["code_exec", "inspect"]
     |                                    .code_blocks = ["ns(graph)"]
     |                                    .has_code = True
     v
  router.write("ai", response,
    metadata={"type": "response",
              "label": "1",
              "tools": ["code_exec", "inspect"]})
     |
     v
  Channel.write()
     +-- store.record(...)              <-- tools list in metadata
     +-- _buffer.append(...)
     +-- if visible: _display(...)
           |
           v
     _formatter.render(...)             <-- ViewFormatter dispatch
           |
           +-- [UserView]:  Panel(Markdown(response), title="ai:1", ...)
           +-- [DebugView]: raw text + metadata dump
           +-- [RawView]:   plain text
           +-- [AISelfView]: shows prompt that was sent
```

### Execution Display Flow (Modified)

```
  for code in classified.code_blocks:
     |
     v
  async_exec(code, namespace)
     |
     v
  router.write("py", code, metadata={"type": "ai_exec", "label": "1"})
     |
     v
  Channel._display() -> formatter.render()
     |
     +-- [UserView]: buffer code, wait for output
     |
     v
  router.write("py", output, metadata={"type": "ai_exec_result", "label": "1"})
     |
     v
  Channel._display() -> formatter.render()
     |
     +-- [UserView]: render grouped Panel(Syntax(code) + Rule + output)
     +-- [DebugView]: prefixed lines with metadata
     +-- [RawView]: plain text
```

## Patterns to Follow

### Pattern 1: Formatter as Strategy

**What:** ViewFormatter is the Strategy pattern. Channel delegates display to a swappable formatter object.
**When:** Any time display behavior needs to change at runtime.
**Why not subclass Channel:** Channels do not change type. A Channel named "ai" is always "ai" -- only its display behavior changes. Subclassing would require replacing Channel objects, breaking references held by router, store, and namespace.

### Pattern 2: Rich-to-ANSI Bridge (Existing)

**What:** All Rich rendering goes through `_rich_to_ansi()` then `print_formatted_text(ANSI(...))`.
**When:** Every formatter that uses Rich renderables.
**Why:** prompt_toolkit's `patch_stdout` requires all terminal output to go through prompt_toolkit's rendering pipeline. Direct `Console.print()` to stdout would corrupt the prompt.

### Pattern 3: Metadata-Driven Rendering

**What:** Formatters decide how to render based on `metadata["type"]`, not by parsing content.
**When:** Choosing between panel styles, grouping decisions, formatting.
**Why:** Parsing content is fragile and duplicates work. The producer (AI eval loop) already knows what kind of content it is producing. Passing that knowledge via metadata is clean and testable.

### Pattern 4: Pure Classification Functions

**What:** `classify_response()` is a pure function -- text in, dataclass out.
**When:** Adding analysis steps to the eval loop.
**Why:** Testable without mocks. No side effects. Can be unit tested with string fixtures.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Rich Console Singleton

**What:** Sharing a single `Console` object across async render calls.
**Why bad:** Rich Console carries state (cursor position, line count, style stack). Concurrent renders from background tasks would corrupt state.
**Instead:** Create a fresh `Console(file=StringIO(), force_terminal=True)` per render call. The `_rich_to_ansi()` helper enforces this.

### Anti-Pattern 2: Channel Subclasses for Views

**What:** `class AIChannel(Channel)`, `class DebugAIChannel(Channel)`, etc.
**Why bad:** The router holds Channel references. Swapping subclasses at runtime means replacing objects in the dict, breaking any external references (namespace["channels"], store bindings).
**Instead:** Composition. The Channel holds a formatter reference that can be swapped. The Channel identity stays stable.

### Anti-Pattern 3: Parsing Content in Formatters

**What:** Formatter checking `if "```python" in content` to decide rendering.
**Why bad:** Duplicates the parsing logic from AI.extract_code(). Fragile. Breaks if markdown quoting changes.
**Instead:** Metadata-driven. The producer tags content with `metadata["type"]` and the formatter trusts the tag.

### Anti-Pattern 4: View Formatter Modifying Content

**What:** Formatter that strips, transforms, or enriches the content string before passing it to Rich.
**Why bad:** The same content is stored in the SessionStore. If formatters modify content, the stored version and displayed version diverge, breaking replay and search.
**Instead:** Formatters render content as-is. Visual framing (panels, colors, syntax highlighting) is additive, not transformative. The content string is immutable through the pipeline.

### Anti-Pattern 5: Tool Call Detection via Claude API tool_use

**What:** Switching `--output-format` to JSON to get tool_use content blocks.
**Why bad:** The AI subprocess uses `--tools ""` which disables all tools. There are no tool_use blocks in the response. Even if tools were enabled, JSON output would require parsing the entire response differently, breaking the existing text-based flow.
**Instead:** Text-based pattern detection via `classify_response()`. The "tools" are code blocks in markdown -- they are already being detected by `extract_code()`. Classification adds semantic labels.

## Integration Summary: New vs Modified vs Unchanged

### New Components

| Component | File | Purpose | Depends On |
|-----------|------|---------|------------|
| ViewFormatter protocol | views.py | Display strategy interface | None |
| UserView | views.py | Framed panel display | Rich Panel, Syntax, Markdown |
| DebugView | views.py | Raw + metadata display | prompt_toolkit FormattedText |
| RawView | views.py | Plain text display | prompt_toolkit FormattedText |
| AISelfView | views.py | AI perspective display | Rich Panel |
| `_rich_to_ansi()` | views.py | Rich renderable to ANSI string | Rich Console, StringIO |
| `classify_response()` | ai.py | Tool call classification | AI.extract_code, ast |
| ResponseClassification | ai.py | Classification result dataclass | None |
| ViewMode enum | shell.py | View mode state | None |

### Modified Components

| Component | File | Change | Risk |
|-----------|------|--------|------|
| `Channel._display()` | channels.py | Delegate to `_formatter` if set, else existing logic | LOW -- backward compatible |
| `Channel.__init__` | channels.py | Add `_formatter` field (default None) | LOW -- new field, optional |
| `AI.__call__()` | ai.py | Add classify_response step, pass tools in metadata | LOW -- additive |
| `ai_prompt.md` | ai_prompt.md | Add tool conventions section | MEDIUM -- behavior change |
| `CortexShell.__init__()` | shell.py | Add view_mode state, view toolbar widget | LOW -- additive |
| `_build_key_bindings()` | shell.py | Add Ctrl+V for view cycling | LOW -- new binding |

### Unchanged Components

| Component | Why Unchanged |
|-----------|---------------|
| `Channel.write()` | Recording, buffering, visibility check -- all the same |
| `ChannelRouter` | Dispatch logic unchanged, formatters are per-channel |
| `SessionStore` | Records content as-is, metadata already supports dicts |
| `AI._send()` | Subprocess invocation unchanged |
| `AI.extract_code()` | Still the core code block extractor |
| `async_exec()` | Execution unchanged |
| `TaskManager` | Task lifecycle unchanged |
| `render_markdown()` | Still exists, used by UserView internally |

## Suggested Build Order

### Phase A: View Formatter Infrastructure

**Build:** ViewFormatter protocol, `_rich_to_ansi()` helper, Channel `_formatter` field, `_display()` delegation.

**Why first:** All other features depend on the formatter dispatch. Without it, new rendering has nowhere to plug in.

**Deliverables:**
- `views.py` with ViewFormatter protocol and `_rich_to_ansi()`
- Modified `Channel` with `_formatter` field and delegation in `_display()`
- Tests: formatter protocol, delegation, backward compatibility when `_formatter is None`

**Validation:** Existing tests pass unchanged (no formatter set = old behavior).

### Phase B: UserView -- Execution Framing

**Build:** UserView formatter with Panel rendering for `ai_exec`, `ai_exec_result`, and `response` types. Buffered exec grouping.

**Why second:** This is the highest-visibility change. Users immediately see the difference. The existing eval loop already produces the right metadata types.

**Deliverables:**
- UserView class in views.py
- Panel rendering for response, exec, and exec_result
- Buffered exec grouping (code + output in one panel)
- Tests: each render path, buffer flush, error output styling

**Validation:** Set `_formatter = UserView()` on `ai` and `py` channels. Run AI conversation. Panels render correctly.

### Phase C: Tool Call Detection

**Build:** `classify_response()`, ResponseClassification dataclass, integration into `AI.__call__()`.

**Why third:** Depends on Phase A (formatters can use tool metadata). Independent of Phase B (classification is metadata enrichment, not display).

**Deliverables:**
- `classify_response()` pure function
- ResponseClassification dataclass
- AI.__call__() modified to classify and pass tools in metadata
- Tests: classification of various response types (code, inspect, import, prose)

**Validation:** AI responses include `tools` in metadata. DebugView shows tool list.

### Phase D: View Mode Switching + Remaining Formatters

**Build:** ViewMode enum, Ctrl+V keybinding, DebugView, RawView, AISelfView, toolbar widget.

**Why last:** Requires all formatters (Phase B), tool metadata (Phase C), and formatter infrastructure (Phase A) to be in place. Multiple views are the user-facing integration of all previous phases.

**Deliverables:**
- ViewMode enum and VIEW_CYCLE
- Ctrl+V keybinding in shell.py
- DebugView, RawView, AISelfView formatters
- View mode toolbar widget
- Tests: mode cycling, formatter swapping, each formatter renders correctly

**Validation:** Ctrl+V cycles through views. Each view shows the same content differently.

### Phase E: AI Prompt Hardening

**Build:** Updated ai_prompt.md with tool conventions.

**Why separate:** Prompt changes are behavioral, not structural. They should be tested empirically after the infrastructure is in place.

**Deliverables:**
- Updated ai_prompt.md
- Empirical testing of AI response quality
- Iteration based on observed behavior

**Validation:** AI produces single code fences per response. AI does not produce unwanted code blocks.

## Sources

### Primary (HIGH confidence)
- Rich Panel docs: https://rich.readthedocs.io/en/stable/panel.html
- Rich Syntax docs: https://rich.readthedocs.io/en/stable/syntax.html
- Rich Group docs: https://rich.readthedocs.io/en/stable/group.html
- Rich Box styles: https://rich.readthedocs.io/en/stable/appendix/box.html
- Rich Console API (StringIO capture): https://rich.readthedocs.io/en/stable/console.html
- prompt_toolkit ANSI class: https://python-prompt-toolkit.readthedocs.io/en/master/pages/reference.html
- Direct codebase analysis: channels.py, ai.py, shell.py, views of all existing test files
- Verified Rich Panel rendering via local `uv run` execution (code + output grouping)

### Secondary (MEDIUM confidence)
- Rich+prompt_toolkit integration discussion: https://github.com/Textualize/rich/discussions/936
- prompt_toolkit patch_stdout behavior: https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1346
- Claude CLI reference (--tools, --output-format): https://code.claude.com/docs/en/cli-reference

---
*Architecture research: 2026-02-14 -- v5.0 multi-view stream framework*
