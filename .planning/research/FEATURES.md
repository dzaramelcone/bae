# Feature Landscape: Cortex v5.0 Stream Views

**Domain:** Multi-view stream framework, AI prompt hardening, tool call interception, execution display framing
**Researched:** 2026-02-14
**Overall confidence:** HIGH for execution display and prompt hardening (well-understood patterns, existing codebase primitives); MEDIUM for multi-view framework (novel design over existing channels); HIGH for tool call interception (regex on known XML format)

---

## Existing Foundation (Already Built)

These are the v4.0 primitives that v5.0 builds on. Understanding them is critical because every v5.0 feature is a transformation layer over existing code, not a greenfield build.

| Component | File | What It Does | v5.0 Hook Point |
|-----------|------|-------------|-----------------|
| `Channel` | `channels.py` | Named output stream with color, visibility, buffer, store integration | Multi-view adds formatter dispatch before `_display()` |
| `ChannelRouter` | `channels.py` | Registry of channels, `write()` dispatches to named channel | View registry attaches to router, not individual channels |
| `AI.__call__` | `ai.py` | Eval loop: send -> extract code -> execute -> feed back -> loop | Tool call interception inserts between send and extract |
| `AI._send` | `ai.py` | Claude CLI subprocess with `--tools ""` and `--strict-mcp-config` | Prompt hardening modifies system prompt loaded here |
| `ai_prompt.md` | `repl/ai_prompt.md` | System prompt for AI agent | Fewshot rejection example added here |
| `render_markdown` | `channels.py` | Rich Markdown -> ANSI string for `[ai]` channel | Execution display uses Rich Panel + Syntax instead |
| `SessionStore.record` | `store.py` | Persists all I/O entries to SQLite | Store view reads these records for cross-AI consumption |

---

## Table Stakes

Features that address known v4.0 tech debt. Without these, the REPL has visible defects.

| Feature | Why Expected | Complexity | Depends On | Notes |
|---------|--------------|------------|------------|-------|
| **AI prompt hardening -- explicit no-tools constraint** | v4.0 UAT-2 test 2 FAILED: AI generates fake tool_use XML with fabricated file paths and invented results. Users see hallucinated tool calls instead of Python code. This is a visible defect, not a nice-to-have. | Low | `ai_prompt.md` | Add explicit "you have NO tools available" constraint to system prompt. The Claude CLI `--tools ""` flag disables tool execution but does not remove tool-calling patterns from the model's behavior -- the internal system prompt still says "In this environment you have access to a set of tools." The model trained on tool-use patterns hallucinates them. The fix is in OUR system prompt, not in CLI flags. |
| **Fewshot rejection example in system prompt** | Telling the model "no tools" is necessary but insufficient. LLMs follow demonstrated patterns more reliably than instructions. A single fewshot showing: attempt tool call, get rejection, correct to Python code -- teaches the model the desired behavior. | Low | `ai_prompt.md`, no-tools constraint above | One example block in the system prompt. Pattern: User asks question, AI starts XML tool call, system says "no tools, use Python", AI writes Python fence. The fewshot makes the constraint concrete. |
| **Tool call interception in eval loop** | Even with prompt hardening, the model may still occasionally emit tool-use XML (especially on first call before the fewshot sinks in). Without interception, the user sees raw XML garbage. With interception, the system catches it, feeds corrective feedback, and the model self-corrects. | Med | `ai.py` eval loop, regex for tool-use XML patterns | Regex-based detection inserted AFTER `_send()` returns, BEFORE `extract_code()`. When detected: (1) show user a brief "[ai] correcting tool call attempt" message, (2) feed rejection text back as the next prompt ("You attempted to use tools. You have no tools. Use Python code fences instead."), (3) continue eval loop. |
| **Deduplicated execution display** | v4.0 UAT-2 test 5 flagged: when AI writes code that the eval loop executes, the code appears in the AI markdown response AND again as `[py]` channel output. User sees the same code 2-3x. This is cosmetic but makes the REPL feel broken. | Med | `ai.py`, `channels.py`, Rich Panel/Syntax | Replace the redundant `[py]` lines for AI-initiated code with framed Rich Panels. AI code block rendered as Panel with syntax highlight and title. Execution output in separate panel below. The AI markdown response still renders on `[ai]`, but eval loop output uses framed display instead of flat `[py]` lines. |

## Differentiators

Features that set cortex apart. Not expected by users, but transform the experience.

| Feature | Value Proposition | Complexity | Depends On | Notes |
|---------|-------------------|------------|------------|-------|
| **Multi-view stream framework** | Same channel data, different formatting for different consumers. The user sees Rich Panels with color. The AI eval loop gets structured text feedback. Another AI (cross-session) gets store records. Debug mode shows raw channel writes. This is the conceptual leap from "channels as display" to "channels as data bus with pluggable views." | Med-High | `channels.py`, new `views.py` module | The Channel currently conflates data flow and display (`write()` calls `_display()` directly). The multi-view framework separates these: `write()` records data + notifies registered views. Each view is a callable that receives `(channel_name, content, metadata)` and decides how to render. The "user view" renders Rich panels. The "AI feedback view" renders structured text. The "store view" already exists (store.record). The "debug view" renders raw `[channel] content` lines. |
| **View registry with debug toggle** | Users can switch between views at runtime. Debug mode shows raw channel data (what v4.0 showed). Rich mode shows framed panels. Raw mode shows unformatted text. Debug mode is invaluable for understanding what the AI sees vs what the user sees. | Low-Med | Multi-view framework above | Simple dict of `{name: ViewFormatter}` on the router. One active view at a time for the terminal. The store view always runs (persistence is not optional). |
| **Framed code + output panels** | AI-initiated code blocks render in a Rich Panel with syntax highlighting and a title bar ("ai:1 code"). Execution output renders in a separate panel below ("output"). Visually groups code and its result. Looks professional. Replaces the flat `[py]` lines with structured visual blocks. | Med | Rich Panel, Rich Syntax, `channels.py` display path | `Panel(Syntax(code, "python", theme="ansi_dark"), title="ai:1 code", border_style="blue")` for code. `Panel(output_text, title="output", border_style="green")` for results. Both rendered through the Rich-to-ANSI-to-prompt_toolkit bridge already proven in v4.0. |
| **AI self-view (structured feedback)** | When the eval loop feeds results back to the AI, it currently sends raw output text. With multi-view, the AI feedback view can structure this more usefully: include the code that was run, whether it succeeded or failed, the output, and what namespace mutations occurred. The AI gets better context for its next iteration. | Med | Multi-view framework, eval loop | Not just "Block 1 output: ..." but structured feedback like "[executed] store.search('query') [success] [output] 3 entries found [namespace] no changes". This helps the AI understand what happened without re-reading its own code. |

## Anti-Features

Features to explicitly NOT build for v5.0.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Streaming display (token-by-token)** | Claude CLI with `--output-format text` returns the complete response. Streaming requires switching to the Anthropic API directly (with API key management, conversation state management, token counting). The current subprocess approach is zero-config. Streaming is a separate milestone. | Keep blocking subprocess call. The framed panel display will make the response feel more polished even without streaming. |
| **AI bash dispatch** | Letting the AI execute bash commands opens a security surface. The AI currently only executes Python in the shared namespace (sandboxed by design -- it can only affect the REPL session). Adding bash would require permission prompting, command allowlisting, and process isolation. | Keep AI execution to Python only. Users can run bash themselves in BASH mode. The AI's system prompt should say "Python code fences only, no bash." |
| **Configurable view per channel** | Tempting to let users set different views per channel (e.g., "rich for ai, raw for py"). But this adds combinatorial complexity to the view system and the UI for managing it. One active view for the terminal is sufficient. | Single active view for terminal display. The store view always persists. Debug view available via toggle. |
| **Custom view plugins** | Extensible view system where users write Python classes that implement a View protocol and register them. YAGNI. The three built-in views (user/rich, debug/raw, AI/structured) cover all known use cases. | Hardcode the three views. If a new view is needed, add it to the codebase. Python is the extension system. |
| **Undo/replay of AI corrections** | When tool call interception fires and the AI self-corrects, the user might want to see what the AI originally tried. But storing and displaying rejected attempts adds complexity with no clear value -- the user cares about the corrected result, not the failed attempt. | Show a brief "[ai] corrected tool call attempt" message. Log the full rejected output to the debug channel. Don't build an undo system. |
| **Semantic parsing of tool-use XML** | Tempting to parse the hallucinated tool calls, extract the intended operation, and translate it to equivalent Python code automatically. But this creates a fragile translation layer between two different execution models. | Simple regex detect + reject + retry. Let the AI figure out the Python equivalent itself. The fewshot in the system prompt guides this. |

## Feature Dependencies

```
AI prompt hardening (system prompt changes)           [no code deps, standalone]
    |
    +---> Fewshot rejection example                   [extends system prompt]
    |
    +---> Tool call interception                      [depends on knowing what to reject]
              |
              +---> Visible correction message        [interception must exist first]
              |
              +---> Corrective feedback in eval loop  [interception triggers feedback]

Multi-view stream framework                           [refactors Channel._display]
    |
    +---> View registry on ChannelRouter              [framework must exist first]
    |         |
    |         +---> Debug view toggle                 [registry must exist first]
    |
    +---> Rich Panel execution display                [view framework renders panels]
    |         |
    |         +---> Framed code blocks                [Panel + Syntax]
    |         |
    |         +---> Framed output blocks              [Panel]
    |         |
    |         +---> Deduplication                     [view controls what renders]
    |
    +---> AI self-view (structured feedback)           [view framework + eval loop]
```

**Critical ordering insight:** Prompt hardening and tool call interception are INDEPENDENT of the multi-view framework. They can (and should) ship first because they fix a visible defect. The multi-view framework is a refactor of the display layer that enables the execution display improvements. Building the view framework first, before the execution display, prevents having to rewrite display code twice.

## Detailed Feature Specifications

### 1. AI Prompt Hardening

**What the system prompt needs:**

The current `ai_prompt.md` says nothing about tools. The Claude CLI `--tools ""` flag disables tool execution but the model's internal system prompt still includes "In this environment you have access to a set of tools you can use..." followed by formatting instructions. When our system prompt (via `--system-prompt`) replaces the default, those tool instructions vanish -- but the model has been fine-tuned on tool-use patterns and will still produce them without explicit counterpressure.

**Required additions to `ai_prompt.md`:**

1. **Explicit constraint block** -- a "## Constraints" section stating: no tools available, no XML tool syntax, Python code fences only, file inspection via Python (pathlib/open), searching via store.search() in Python.

2. **Fewshot rejection example** -- a "## Example" section demonstrating the correct behavior. User asks a question that might tempt tool use (e.g., "what files are in this directory?"). The correct response is a Python code fence with `os.listdir('.')`. The example explicitly marks the XML tool-call pattern as WRONG and shows it would be rejected. This is the single most effective prompt engineering technique for constraining behavior -- demonstrated examples outweigh instructions.

**Why fewshot over instruction-only:**

Research from LangChain and prompt engineering literature confirms that few-shot prompting greatly boosts model performance on tool-calling tasks. The inverse applies equally -- fewshot examples of rejection patterns train the model to avoid those patterns. The OWASP Prompt Injection Prevention cheat sheet recommends repeating critical rules at multiple points in the system prompt, especially near the end. The constraint block at the top + fewshot example in the middle + the existing "1 fence per turn max" rule near the end creates three reinforcement points.

**Confidence:** HIGH -- well-established prompt engineering technique, specific to known failure mode.

### 2. Tool Call Interception

**What to detect:**

Claude CLI's tool-use output follows a specific XML format. Based on the Claude API documentation and observed behavior, the model outputs tool calls as structured content blocks. When running via `--output-format text`, the text output may contain XML-like tool-call patterns. The observed hallucinated patterns from v4.0 UAT-2 include:

- `<function_calls>` / `</function_calls>` wrapper tags
- `<invoke name="ToolName">` blocks
- `<parameter name="param">value</parameter>` inner tags
- Occasionally `<tool_use>` / `<antml_invoke>` variant tags

**Regex patterns for detection:**

```python
TOOL_CALL_RE = re.compile(
    r'<(?:function_calls|tool_use|antml_invoke|invoke)\b',
    re.IGNORECASE,
)
```

This catches the opening tag of any tool-call pattern. No need to parse the full XML structure -- if the model is emitting ANY of these tags, it has gone off-script and needs correction.

**Interception flow:**

```
AI._send() returns response text
    |
    v
Check TOOL_CALL_RE.search(response)
    |
    +-- No match: proceed to extract_code() as normal
    |
    +-- Match found:
         1. router.write("debug", full_response)      # log for debugging
         2. router.write("ai", "[correcting tool call attempt]", metadata={"type": "correction"})
         3. Feed rejection prompt back to AI:
            "You just attempted to use tools (XML function_calls/invoke).
             You have NO tools. Rewrite your response using Python code fences only."
         4. response = await self._send(rejection_prompt)
         5. Continue eval loop with corrected response
```

**Key design decisions:**

- Interception counts against `max_eval_iters` to prevent infinite correction loops
- The full rejected response is logged to the debug channel (not shown to user)
- The user sees only a brief correction notice, not the raw XML
- The rejection prompt is fed as a `--resume` continuation, so the AI has full context of what it tried and why it was rejected

**Confidence:** HIGH -- regex on known XML patterns, straightforward control flow insertion.

### 3. Multi-View Stream Framework

**Architecture:**

The current Channel class conflates data recording and display. `Channel.write()` does three things: (1) records to store, (2) appends to buffer, (3) calls `_display()`. The multi-view framework separates concern (3) into pluggable formatters.

**View protocol:**

```python
class View(Protocol):
    """A formatter that consumes channel data."""

    def render(self, channel: str, content: str, metadata: dict | None) -> None:
        """Format and display content from a channel write."""
        ...
```

**Built-in views:**

| View | What It Renders | When Active |
|------|----------------|-------------|
| `UserView` | Rich Panels for AI code/output, Rich Markdown for AI text, color-coded `[channel]` prefix for everything else | Default terminal view |
| `DebugView` | Raw `[channel] content` lines for everything, no Rich formatting | Toggled via debug command |
| `AIFeedbackView` | Structured text for eval loop feedback (not rendered to terminal) | Always active, consumed programmatically by `AI.__call__` |

**How Channel.write() changes:**

```python
# Before (v4.0):
def write(self, content, **kwargs):
    self.store.record(...)
    self._buffer.append(content)
    if self.visible:
        self._display(content)

# After (v5.0):
def write(self, content, **kwargs):
    self.store.record(...)
    self._buffer.append(content)
    # Notify all registered views
    for view in self._router.active_views():
        view.render(self.name, content, kwargs.get("metadata"))
```

**The router owns the view registry, not individual channels.** This is important because views span channels -- the UserView needs to know about writes to both "ai" and "py" channels to coordinate framed display.

**Confidence:** MEDIUM -- novel design, but the primitives (Channel, Router, Rich rendering) are all proven. The risk is in the refactor, not the concept.

### 4. Execution Display (Framed Panels)

**What changes for the user:**

v4.0 display when AI executes code:
```
[ai] Here's what's in your namespace:
[ai]
[ai] ```python
[ai] ns()
[ai] ```
[py] ns()                          <-- redundant, same code shown again
[py] graph  Graph  Graph(start=...)
[py] ai     AI     ai:1 -- ...
[ai] You have a graph with 3 nodes and an AI session active.
```

v5.0 display with framed panels:
```
[ai] Here's what's in your namespace:

+-- ai:1 code ----------------------------------------+
| ns()                                                 |
+------------------------------------------------------+
+-- output --------------------------------------------+
| graph  Graph  Graph(start=...)                       |
| ai     AI     ai:1 -- ...                           |
+------------------------------------------------------+

[ai] You have a graph with 3 nodes and an AI session active.
```

**Implementation using Rich:**

```python
from rich.panel import Panel
from rich.syntax import Syntax

def render_code_panel(code: str, label: str) -> str:
    """Render code in a framed panel with syntax highlighting."""
    syntax = Syntax(code, "python", theme="ansi_dark", padding=0)
    panel = Panel(syntax, title=f"{label} code", border_style="blue", expand=True)
    buf = StringIO()
    console = Console(file=buf, width=terminal_width(), force_terminal=True)
    console.print(panel)
    return buf.getvalue()

def render_output_panel(output: str, label: str = "output") -> str:
    """Render execution output in a framed panel."""
    panel = Panel(output.rstrip(), title=label, border_style="green", expand=True)
    buf = StringIO()
    console = Console(file=buf, width=terminal_width(), force_terminal=True)
    console.print(panel)
    return buf.getvalue()
```

**Where this hooks into the eval loop:**

In `AI.__call__`, the current code does:
```python
self._router.write("py", code, mode="PY", metadata={"type": "ai_exec"})
self._router.write("py", output, mode="PY", metadata={"type": "ai_exec_result"})
```

With framed display, the metadata `type` field drives the UserView's rendering decision:
- `type: "ai_exec"` -> render as code panel with syntax highlighting
- `type: "ai_exec_result"` -> render as output panel
- Other `[py]` writes (user-initiated) -> render as normal `[py]` prefix lines

This means the view framework uses metadata to decide rendering, NOT the channel name. The channel is still "py" for both AI-executed and user-executed code. The difference is in the metadata.

**Deduplication strategy:**

The AI markdown response (on `[ai]` channel) includes the code block in its text. The eval loop also writes the same code to `[py]` channel. The deduplication approach: the UserView renders `[ai]` markdown as before (including the code block in the markdown), but renders `type: "ai_exec"` writes as framed panels instead of flat `[py]` lines. The user still sees the code in the AI response markdown AND in the panel, but the panel provides a visually distinct execution frame that makes it feel intentional rather than redundant.

Alternative: strip code blocks from the AI markdown before rendering on `[ai]`, showing ONLY the framed panels. This is cleaner but requires modifying the AI response text before display, which adds complexity. Start with the dual-display approach and iterate.

**Confidence:** HIGH for Rich Panel/Syntax usage (documented API, proven in v4.0 bridge). MEDIUM for deduplication strategy (needs UX iteration).

## MVP Recommendation

Build in this order:

### Phase 1: Prompt Hardening + Tool Call Interception

**Prioritize:**
1. Add constraints section to `ai_prompt.md`
2. Add fewshot rejection example to `ai_prompt.md`
3. Add `TOOL_CALL_RE` regex to `ai.py`
4. Add interception check in `AI.__call__` after `_send()`, before `extract_code()`
5. Correction message on `[ai]` channel, rejection prompt fed back to AI

**Why first:** Fixes the most visible defect (hallucinated tool calls). Low complexity. No refactoring needed. Immediately testable -- run the REPL, ask the AI to do something, verify it uses Python not XML.

**Defer from this phase:** Multi-view framework, framed panels. Those are display improvements, not correctness fixes.

### Phase 2: Multi-View Framework

**Prioritize:**
1. Extract View protocol (callable or Protocol class)
2. Build UserView (current display behavior, extracted from Channel._display)
3. Build DebugView (raw [channel] content lines)
4. View registry on ChannelRouter
5. Refactor Channel.write() to notify views instead of calling _display() directly
6. Debug toggle command or keybinding

**Why second:** This is the structural refactor that enables phase 3. Building it before the execution display means the panel rendering hooks into the view system cleanly instead of being bolted onto the existing Channel._display.

### Phase 3: Framed Execution Display

**Prioritize:**
1. `render_code_panel()` and `render_output_panel()` using Rich Panel + Syntax
2. UserView routes `type: "ai_exec"` metadata to code panels
3. UserView routes `type: "ai_exec_result"` metadata to output panels
4. AI self-view produces structured feedback text for eval loop
5. Verify deduplication -- user sees framed panels, not redundant `[py]` lines

**Why third:** Depends on the view framework from phase 2. The framed display is the visible payoff of the multi-view refactor.

**Defer from all phases:**
- Streaming display (separate milestone)
- AI bash dispatch (security scope)
- Custom view plugins (YAGNI)

## Sources

**Official Documentation (HIGH confidence):**
- [Rich Panel docs](https://rich.readthedocs.io/en/stable/panel.html) -- Panel API, border styles, titles
- [Rich Syntax docs](https://rich.readthedocs.io/en/stable/syntax.html) -- Syntax highlighting, themes, line numbers
- [Rich Panel reference](https://rich.readthedocs.io/en/stable/reference/panel.html) -- Full API reference
- [Claude CLI reference](https://code.claude.com/docs/en/cli-reference) -- `--tools ""` flag, `--system-prompt`, `--output-format`
- [Claude tool use implementation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use) -- Tool call XML structure, content block format

**Research and Best Practices (MEDIUM confidence):**
- [LangChain few-shot prompting for tool calling](https://blog.langchain.com/few-shot-prompting-to-improve-tool-calling-performance/) -- Fewshot technique validation
- [OWASP LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html) -- System prompt hardening patterns
- [Prompt Engineering Guide: Few-Shot](https://www.promptingguide.ai/techniques/fewshot) -- Fewshot prompting fundamentals

**Codebase References (HIGH confidence):**
- `bae/repl/ai.py` -- AI class, eval loop, _send(), extract_code()
- `bae/repl/channels.py` -- Channel, ChannelRouter, render_markdown()
- `bae/repl/ai_prompt.md` -- Current system prompt
- `bae/repl/shell.py` -- CortexShell, dispatch, mode handling
- `.planning/phases/20-ai-eval-loop/20-UAT-2.md` -- v4.0 defect documentation (tests 2 and 5)

**Design Pattern References (MEDIUM confidence):**
- [Observer pattern](https://en.wikipedia.org/wiki/Observer_pattern) -- Foundation for multi-view notification
- [Rich + prompt_toolkit ANSI bridge](https://github.com/Textualize/rich/discussions/2648) -- Proven rendering bridge pattern

---

*Research conducted: 2026-02-14*
*Focus: Feature landscape for cortex v5.0 Stream Views milestone*
