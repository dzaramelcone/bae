# Technology Stack: v5.0 Stream Views, Prompt Hardening, Tool Interception

**Project:** Bae v5.0 -- Multi-view stream framework, AI prompt hardening, tool call interception, execution display framing
**Researched:** 2026-02-14
**Overall confidence:** HIGH

---

## Verdict: No New Dependencies

Every capability needed for v5.0 is already available in the existing stack. The work is architecture and prompt engineering, not procurement.

| Feature | Provided By | Already Installed | Verified |
|---------|-------------|-------------------|----------|
| Multi-view stream framework | `rich.panel.Panel`, `rich.syntax.Syntax`, `rich.console.Group` | Yes (rich 14.3.2) | Tested locally |
| Execution display framing | `rich.panel.Panel` + `rich.syntax.Syntax` | Yes | ANSI pipeline tested, 1133 chars output |
| View formatter protocol | `typing.Protocol` or `abc.ABC` | Yes (stdlib) | Import verified |
| Tool call XML detection | `re` module | Yes (stdlib) | Pattern tested against false positives |
| AI prompt hardening | System prompt text file (ai_prompt.md) | N/A (text, not a library) | Anthropic docs confirm technique |
| Fewshot tool rejection | `<example>` tags in system prompt | N/A (text) | Anthropic multishot docs confirm |
| Debug view toggle | Existing `ChannelRouter` visibility + new view layer | Yes | In production (channels.py) |

---

## Existing Stack (Unchanged for v5.0)

### Core -- No Version Bumps Needed

| Technology | Installed | Purpose | Status |
|------------|-----------|---------|--------|
| Python | 3.14+ | Runtime | Unchanged |
| Rich | 14.3.2 | Terminal rendering | Already has Panel, Syntax, Group, Rule, Text |
| prompt_toolkit | 3.0.52 | REPL input + ANSI display | Already integrated with Rich via ANSI pipeline |
| Pygments | 2.19.2 | Syntax highlighting (used by Rich.Syntax internally) | Unchanged |
| re (stdlib) | 3.14 | Regex for tool call detection | Unchanged |

### pyproject.toml -- No Changes

```toml
# Current dependencies -- UNCHANGED for v5.0
dependencies = [
    "pydantic>=2.0",
    "pydantic-ai>=0.1",
    "dspy>=2.0",
    "typer>=0.12",
    "prompt-toolkit>=3.0.50",
    "pygments>=2.19",
    "rich>=14.3",
]
```

---

## Rich Components for v5.0 Features

### Integration Path: Rich to prompt_toolkit (Already Proven)

The codebase already has this exact pattern in `channels.py`:

```python
# channels.py line 30-40 -- EXISTING production code
def render_markdown(text: str, width: int | None = None) -> str:
    buf = StringIO()
    console = Console(file=buf, width=width, force_terminal=True)
    console.print(Markdown(text))
    return buf.getvalue()
```

v5.0 generalizes this to render any Rich renderable:

```python
def render_rich(renderable, width: int | None = None) -> str:
    """Render any Rich object to ANSI string for prompt_toolkit display."""
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

**Confidence: HIGH** -- This is the same pattern already shipping in production, just applied to Panel/Syntax instead of Markdown.

### Panel + Syntax for Execution Display

Tested against installed Rich 14.3.2:

```python
from rich.panel import Panel
from rich.syntax import Syntax
from rich.console import Group
from rich.text import Text

# Code block framing
code_panel = Panel(
    Syntax(code, "python", theme="monokai"),
    title="[bold green]Code",
    border_style="green",
    padding=(0, 1),
)

# Output framing
output_panel = Panel(
    Text(output_text),
    title="[bold blue]Output",
    border_style="blue",
    padding=(0, 1),
)

# Composed display
framed = Group(code_panel, output_panel)
```

**Test results:**
- Panel renders correctly with ANSI escape codes
- Syntax highlighting works inside Panel (monokai theme)
- Group composes multiple panels sequentially
- Total ANSI output: 1133 chars for a two-panel group
- Output passes through `print_formatted_text(ANSI(ansi_str))` correctly

### Rich Components Reference

| Component | Import | v5.0 Use | API Stability |
|-----------|--------|----------|---------------|
| `Panel` | `rich.panel` | Bordered frame with title for code/output sections | Stable since Rich 10+ |
| `Syntax` | `rich.syntax` | Python syntax highlighting inside code panels | Stable, uses Pygments internally |
| `Group` | `rich.console` | Compose code panel + output panel as single renderable | Stable since Rich 12+ |
| `Text` | `rich.text` | Styled text for output sections | Stable core class |
| `Rule` | `rich.rule` | Horizontal dividers between view sections | Stable since Rich 10+ |
| `Console` | `rich.console` | Render to StringIO for ANSI capture | Core class, stable |

---

## Tool Call XML Detection (stdlib re)

### Pattern Design

Claude emits tool-call-shaped XML when it attempts to use tools despite being told not to. The patterns are well-documented from Claude Code system prompts and confirmed via the [langchain-aws issue #521](https://github.com/langchain-ai/langchain-aws/issues/521):

```python
import re

# Detect tool-use XML in AI text responses
TOOL_CALL_RE = re.compile(
    r"<(?:function_calls|tool_use|invoke\s|antml:)",
)
```

**Pattern coverage:**

| Pattern | Matches | Example |
|---------|---------|---------|
| `function_calls` | Legacy Claude tool call wrapper | `<function_calls>` |
| `tool_use` | Tool use block tag | `<tool_use>` |
| `invoke\s` | Individual tool invocation (with attribute) | `<invoke name="Bash">` |
| `antml:` | Anthropic-namespaced XML tags | `<invoke>`, `<function_calls>` |

**False positive testing:**

| Input | Match? | Correct? |
|-------|--------|----------|
| `"Here is some normal text"` | No | Yes |
| `"Use the <code>print()</code> function"` | No | Yes |
| `"Regular XML like <div>hello</div>"` | No | Yes |
| `"The <invoke> element in XSLT"` | No | Yes (no trailing space, no attribute) |

**Why not an XML parser:** We are matching known fixed prefixes from a closed set of patterns, not parsing arbitrary XML. The tool call tags are structurally distinct from any legitimate content in a Python REPL context. A regex is simpler, faster, and correct for this use case.

**Confidence: MEDIUM** -- Patterns confirmed from current Claude behavior. Claude may emit new patterns in future model versions. Mitigation: the regex is trivially extensible by adding new alternations.

---

## AI Prompt Hardening (No Library)

### Current State

The system prompt lives at `bae/repl/ai_prompt.md` (plain markdown file, loaded by `_load_prompt()`). v5.0 extends this file with:

1. **Explicit no-tools constraint** in the Rules section
2. **Fewshot examples** showing tool call rejection

### CLI-Level Tool Restriction (Already Active)

The `AI._send()` method already passes restrictive flags:

```python
# ai.py line 133-140 -- EXISTING production code
cmd = [
    "claude",
    "-p", prompt,
    "--model", self._model,
    "--output-format", "text",
    "--tools", "",              # Disables all built-in tools
    "--strict-mcp-config",      # Ignores all MCP configs
    "--setting-sources", "",    # Ignores user/project/local settings
]
```

**Confirmed via [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference):**
- `--tools ""` -- "Use `""` to disable all" built-in tools
- `--strict-mcp-config` -- "Only use MCP servers from `--mcp-config`, ignoring all other MCP configurations"
- `--setting-sources ""` -- empty string disables all setting sources

This is the **primary defense**. The AI prompt hardening and tool call interception are **secondary defenses** for when Claude generates tool-call-shaped XML in its text output despite tools being disabled at the API level.

### Fewshot Prompt Engineering Pattern

Anthropic's [multishot prompting guide](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/multishot-prompting) confirms:
- 3-5 diverse examples dramatically improve accuracy and consistency
- Examples should be wrapped in `<example>` tags
- Examples showing both correct behavior AND explicit rejection of incorrect behavior are most effective

The prompt extension pattern:

```markdown
## Rules
...
- You have NO tools. You cannot use Bash, Read, Write, Edit, or any MCP tool.
- If you want to run code, write a ```python``` fence. The REPL executes it.
- NEVER emit XML tool-call tags. You are in text-only mode.

## Examples

<example>
User: list the files in the current directory
You:
```python
import os
os.listdir(".")
```
</example>

<example>
User: read the contents of main.py
You:
```python
with open("main.py") as f:
    print(f.read())
```
</example>

<example>
User: run git status
You:
```python
import subprocess
result = subprocess.run(["git", "status"], capture_output=True, text=True)
print(result.stdout)
```
</example>
```

**Key design principle:** Every fewshot shows the AI using Python code fences instead of tool calls. The AI learns by example that its execution path is always `write Python -> REPL executes -> see output`, never `call tool -> tool returns`.

**Confidence: HIGH** -- Anthropic's official documentation confirms this technique. The specific examples are domain-appropriate for a Python REPL context.

---

## What NOT to Add

| Temptation | Why Not | What Instead |
|------------|---------|--------------|
| `lxml` / `xml.etree` / `defusedxml` | Tool call detection is prefix matching against 4 known patterns, not XML parsing. Regex is correct and simpler. | `re.compile()` with 4 alternations |
| `textual` (Rich TUI framework) | Full-screen TUI. Project uses scrollback terminal. Explicitly out of scope since v4.0 requirements. | Rich Panel/Syntax rendered to ANSI, displayed via prompt_toolkit |
| `jinja2` / prompt templating library | System prompt is a single markdown file. String concatenation is sufficient. YAGNI. | Plain f-strings or string concatenation |
| Any streaming library | Claude CLI subprocess returns complete responses via `--output-format text`. No token streaming to handle. | Complete response processing after subprocess returns |
| `tiktoken` / token counting | Token budget management for prompt context is done by character truncation (existing `MAX_CONTEXT_CHARS = 2000`). Token counting adds complexity for marginal accuracy improvement. | Character-based truncation (already implemented) |
| New Rich version | Rich 14.3.2 has everything needed. No features in newer versions are required. | Pin at `>=14.3` |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Execution display | Rich Panel + Syntax | Raw ANSI escape codes | Panel gives borders, titles, padding for free. Hand-rolling ANSI is error-prone and unmaintainable. |
| Execution display | Rich Panel + Syntax | Textual widgets | Textual is a full TUI framework. Overkill for rendering framed code blocks in scrollback output. |
| Tool detection | `re` regex | XML parser (ElementTree) | Not parsing XML. Pattern matching 4 known prefixes. Regex is correct, simpler, and has zero failure modes from malformed XML. |
| Tool detection | `re` regex | String `.startswith()` checks | Regex handles the patterns more concisely and allows future extension. Both are correct; regex is marginally more maintainable. |
| Prompt hardening | Fewshot in system prompt | Fine-tuned model | Cannot fine-tune Claude. System prompt engineering is the only lever. |
| Prompt hardening | `<example>` tags | Separate instruction file | Current pattern already loads from `ai_prompt.md`. Keeping everything in one file is simpler. |
| View framework | Protocol-based formatters | Inheritance hierarchy | Protocol (structural typing) allows any object with the right method to be a formatter. No coupling to a base class. Matches existing Python conventions. |

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Rich Panel/Syntax/Group API | HIGH | Tested against installed 14.3.2. All imports verified. ANSI pipeline tested end-to-end. |
| Rich-to-prompt_toolkit pipeline | HIGH | Pattern already exists in production (`render_markdown` in channels.py). Same integration path for Panel/Syntax. |
| Claude CLI `--tools ""` behavior | HIGH | Verified via [official CLI reference docs](https://code.claude.com/docs/en/cli-reference). Already in use in `ai.py`. |
| Tool call XML patterns | MEDIUM | Confirmed from [langchain-aws#521](https://github.com/langchain-ai/langchain-aws/issues/521) and Claude Code system prompt analysis. Claude may emit new patterns in future versions. |
| Fewshot prompt engineering | HIGH | Anthropic [official multishot docs](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/multishot-prompting) confirm technique. |
| No new deps needed | HIGH | All imports verified against installed packages via Python runtime check. |

---

## Sources

### HIGH Confidence
- Rich 14.3.2: tested locally against installed version (Panel, Syntax, Group, Console, Text, Rule all verified)
- `bae/repl/channels.py` lines 30-40: existing `render_markdown()` Rich-to-ANSI pattern (production code)
- `bae/repl/ai.py` lines 133-140: existing `--tools ""` CLI flag usage (production code)
- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference): `--tools ""` disables all built-in tools
- [Anthropic Multishot Prompting Guide](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/multishot-prompting): fewshot example patterns with `<example>` tags

### MEDIUM Confidence
- [langchain-aws #521](https://github.com/langchain-ai/langchain-aws/issues/521): Claude XML tool call format (`<function_calls>`, `<invoke>`, etc.)
- Tool call regex false positive analysis: tested against 4 input cases, but untested against full corpus of possible AI outputs

---

*Stack research for v5.0: 2026-02-14*
*Verdict: Zero new dependencies. Build with what's installed.*
