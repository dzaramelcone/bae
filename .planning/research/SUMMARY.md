# Project Research Summary

**Project:** Bae v5.0 -- Multi-view stream framework, AI prompt hardening, tool call interception, execution display framing
**Domain:** REPL enhancement — multi-view display system with AI behavioral guardrails
**Researched:** 2026-02-14
**Confidence:** HIGH

## Executive Summary

v5.0 addresses critical v4.0 defects while introducing a multi-view display framework that transforms how channel data is consumed. The core problem: AI hallucinates tool-use XML despite CLI-level tool restrictions, and execution output appears redundant/unprofessional. The solution requires no new dependencies — every capability exists in the current stack (Rich 14.3.2, prompt_toolkit 3.0.52, Python stdlib).

The recommended approach layers three independent improvements: (1) prompt hardening with fewshot rejection examples to train the AI away from tool-use patterns, (2) tool call interception to catch and correct XML hallucinations that slip through, and (3) a view formatter framework that separates channel data from presentation, enabling Rich Panel framing for execution displays while preserving raw access for debugging. These work together but ship independently — prompt hardening fixes the most visible defect, view framework enables polished display.

Key risks center on over-constraining the AI prompt (which killed helpful behaviors in early v4.0) and breaking the existing Rich-to-prompt_toolkit ANSI bridge (which would corrupt terminal display). Both are mitigated through empirical testing against existing UAT cases and strict adherence to the StringIO capture pattern already proven in production.

## Key Findings

### Recommended Stack

**Verdict: Zero new dependencies.** Every v5.0 capability is provided by installed packages or stdlib modules. The work is architecture and prompt engineering, not procurement.

**Core technologies:**
- **Rich 14.3.2**: Provides Panel, Syntax, Group, Rule for framed displays — already installed, tested locally, API stable since Rich 10+
- **prompt_toolkit 3.0.52**: REPL and patch_stdout integration already proven in channels.py render_markdown() — same ANSI bridge pattern extends to Panel/Syntax
- **re (stdlib)**: Tool call XML detection via 4 known patterns (`<function_calls>`, `<tool_use>`, `<invoke>`, `<`) — false positive tested against legitimate code
- **typing.Protocol (stdlib)**: ViewFormatter interface for pluggable display strategies — no coupling to base classes
- **ai_prompt.md (text)**: Fewshot examples documented by Anthropic multishot guide — 3-5 examples dramatically improve constraint compliance

**Critical constraint:** All Rich rendering MUST go through `Console(file=StringIO(), force_terminal=True)` then `print_formatted_text(ANSI(...))`. Direct Console.print() to stdout bypasses patch_stdout and corrupts the REPL prompt. This pattern exists in production (channels.py:30-40) and must be preserved.

### Expected Features

Research structured features into table stakes (fix defects), differentiators (transform experience), and anti-features (explicitly avoid).

**Must have (table stakes):**
- **AI prompt hardening** — v4.0 UAT-2 test 2 FAILED: AI generates fake tool_use XML with fabricated results. Users see hallucinated tool calls instead of Python code. Explicit "no tools" constraint + fewshot rejection examples address this.
- **Tool call interception** — Even with prompt hardening, occasional XML slips through. Interception catches it, feeds corrective feedback, AI self-corrects. Regex on known patterns inserted between _send() and extract_code().
- **Deduplicated execution display** — v4.0 UAT-2 test 5: code appears in AI markdown AND [py] channel output, 2-3x duplication. Rich Panel frames with syntax highlighting replace redundant [py] lines.

**Should have (competitive):**
- **Multi-view stream framework** — Same channel data, different formatters for different consumers. User sees Rich Panels, AI gets structured feedback, debug shows raw data, cross-session gets store records. Conceptual leap from "channels as display" to "channels as data bus with pluggable views."
- **Framed code + output panels** — AI code blocks render in Panel with syntax highlighting and title ("ai:1 code"). Output in separate panel below ("output"). Visually groups execution context. Professional appearance replacing flat prefixed lines.
- **View mode cycling** — Ctrl+V toggles UserView (rich), DebugView (raw+meta), RawView (unformatted), AISelfView (what AI sees). Debug invaluable for understanding AI perspective vs user perspective.

**Defer (anti-features for v5.0):**
- **Streaming display** — Claude CLI with `--output-format text` returns complete responses. Streaming requires Anthropic API directly (key management, conversation state). Separate milestone.
- **AI bash dispatch** — Security surface. AI execution sandboxed to Python REPL namespace. Bash requires permission prompts, allowlisting, process isolation.
- **Custom view plugins** — YAGNI. Three built-in views (user, debug, AI-self) cover all known use cases. Python is the extension system.

### Architecture Approach

v5.0 extends the existing Channel/ChannelRouter display pipeline with a ViewFormatter strategy pattern. Currently Channel.write() -> Channel._display() directly renders via print_formatted_text. The view framework inserts a formatter layer: Channel.write() -> Channel._display() -> formatter.render(). The formatter is swappable at runtime, enabling view mode toggling without changing channel identity or breaking references held by router/store/namespace.

**Major components:**

1. **ViewFormatter protocol (views.py)** — Strategy interface with render(channel_name, color, content, metadata). Channel delegates _display() to formatter when set, falls back to existing logic when None (backward compatible, zero test failures).

2. **Concrete formatters (UserView, DebugView, RawView, AISelfView)** — Each receives same channel data, renders differently. UserView uses Rich Panel/Syntax for framed execution display. DebugView shows raw content + full metadata. All use _rich_to_ansi() helper enforcing StringIO capture pattern.

3. **Tool call classification (classify_response in ai.py)** — Pure function analyzing AI responses for "tool patterns" (code blocks, namespace inspection, store queries, imports). Returns dataclass with text, tools list, code blocks. Inserted between _send() and extract_code(). Metadata-driven rendering uses tool list to decide framing style.

4. **AI prompt hardening (ai_prompt.md)** — Adds explicit no-tools constraint and fewshot rejection example. Current prompt says nothing about tools; Claude CLI internal prompt includes tool instructions. Model fine-tuned on tool-use patterns produces them without explicit counterpressure. Fewshot teaches by example: attempted tool call -> rejection -> correct Python code.

5. **View mode state (shell.py)** — CortexShell gains view_mode field, Ctrl+V keybinding cycles views. On cycle, update formatter on each channel. Toolbar shows active view. Simple dict mapping ViewMode enum to formatter instances.

### Critical Pitfalls

Research identified 12 pitfalls across critical/moderate/minor severity. Top 5 that would cause rewrites or major regressions:

1. **ANSI escape contamination in nested Rich rendering** — Wrapping pre-rendered ANSI strings in Rich Panel breaks box-drawing width calculations. Panel must wrap Markdown OBJECT in renderable tree, not ANSI string output. Single render pass with composed renderables (`Panel(Markdown(text))`), never two passes.

2. **Over-constraining AI prompt kills helpful behaviors** — Too many NEVER/MUST NOT constraints shift model toward compliance over helpfulness. v4.0 already calibrated "code when needed" balance. Adding heavy-handed "no tools" risks breaking it. Frame as positive guidance ("use Python for computation"), test with existing UAT prompts (natural NL, code when appropriate).

3. **Multi-view abstraction breaks existing Channel display** — Introducing formatter layer risks blank output, double-rendering, lost content if view has bugs. Must be opt-in per channel with None default (existing behavior). Zero tolerance for existing test failures. Build default path first, verify zero regressions, then add custom formatters.

4. **Tool call interception regex matches normal code** — XML patterns appear legitimately in Python (HTML processing, f-strings, Rich markup, docstrings). Interception must scan OUTSIDE code fences only. Require structural match (full `<invoke name="...">` block), not keyword match. False positive injects confusing correction feedback.

5. **Execution display deduplication removes useful information** — v4.0 duplication is CODE appearing twice (AI markdown + [py] ai_exec), not results. Suppress CODE echo ([py] with type=ai_exec), display RESULTS ([py] with type=ai_exec_result). User needs to see execution output. Store records both regardless of display suppression.

## Implications for Roadmap

Based on dependency analysis and pitfall severity, suggested phase structure decouples behavioral fixes from display refactoring:

### Phase 1: AI Prompt Hardening + Tool Call Interception

**Rationale:** Fixes the most visible v4.0 defect (hallucinated tool calls) with lowest complexity and zero refactoring. Independent of multi-view framework. Immediately testable against UAT-2 failure cases.

**Delivers:**
- Updated ai_prompt.md with explicit no-tools constraint and fewshot rejection example
- Tool call detection regex (TOOL_CALL_RE matching 4 XML patterns)
- Interception in AI.__call__() between _send() and extract_code()
- Corrective feedback loop (1 attempt max to avoid amplification)

**Addresses:**
- FEATURES.md table stakes: "AI prompt hardening" and "tool call interception"
- v4.0 UAT-2 test 2 failure (fake tool_use XML with fabricated results)

**Avoids:**
- Pitfall #2 (over-constraining) via positive framing and UAT regression testing
- Pitfall #4 (false positive regex) via code fence exclusion and structural matching
- Pitfall #7 (correction amplification) via max_corrections=1 limit

**Research flag:** Standard patterns. Anthropic multishot docs + langchain-aws issue #521 provide complete guidance. No deeper research needed.

---

### Phase 2: Multi-View Formatter Framework

**Rationale:** Structural refactor enabling Phase 3. Building view framework BEFORE execution display prevents rewriting display code twice. Formatters ship with default (None) maintaining existing behavior — zero existing test failures required.

**Delivers:**
- ViewFormatter protocol in views.py
- _rich_to_ansi() helper enforcing StringIO pattern
- Channel._formatter field (default None)
- Channel._display() delegation (if formatter set, delegate; else existing logic)
- Backward compatibility tests

**Addresses:**
- FEATURES.md differentiator: "Multi-view stream framework" conceptual foundation
- Architecture pattern: formatter as strategy, metadata-driven rendering

**Avoids:**
- Pitfall #3 (breaking existing display) via opt-in default=None
- Pitfall #8 (patch_stdout bypass) via _rich_to_ansi() factory enforcing StringIO
- Pitfall #10 (global debug state) via formatter swap not flag

**Research flag:** Novel design over existing primitives. May need iterative refinement as formatters are built. Not complex enough for dedicated research-phase; handle in planning review.

---

### Phase 3: UserView + Framed Execution Display

**Rationale:** Depends on Phase 2 formatter framework. Highest-visibility UX improvement. Existing eval loop already produces right metadata types (ai_exec, ai_exec_result). Rich Panel/Syntax tested locally, API stable.

**Delivers:**
- UserView formatter class
- render_code_panel() and render_output_panel() using Rich Panel + Syntax
- Buffered exec grouping (code + output in single Panel)
- Metadata-driven rendering for ai_exec and ai_exec_result types
- Deduplication (suppress CODE echo, display RESULTS)

**Addresses:**
- FEATURES.md table stakes: "Deduplicated execution display"
- FEATURES.md differentiator: "Framed code + output panels"
- v4.0 UAT-2 test 5 (code appears 2-3x)

**Avoids:**
- Pitfall #1 (ANSI contamination) via single render pass with composed renderables
- Pitfall #5 (removing results) via type-based suppression (ai_exec only, not ai_exec_result)
- Pitfall #6 (width desync) via Console handling Panel borders internally
- Pitfall #12 (empty frames) via skipping frame when output is empty

**Research flag:** Standard patterns. Rich Panel/Syntax well-documented, ANSI bridge proven in production. No research needed.

---

### Phase 4: Tool Call Classification + Remaining Formatters

**Rationale:** Depends on Phase 2 (formatters can consume tool metadata) but independent of Phase 3 (classification enriches metadata, not display). Delivers DebugView, RawView, AISelfView for view mode cycling. Includes Ctrl+V keybinding and toolbar.

**Delivers:**
- classify_response() pure function
- ResponseClassification dataclass (text, tools list, code blocks, has_code)
- AI.__call__() integration passing tools in metadata
- DebugView, RawView, AISelfView formatters
- ViewMode enum, VIEW_CYCLE, Ctrl+V keybinding
- View mode toolbar widget

**Addresses:**
- FEATURES.md differentiator: "View registry with debug toggle"
- FEATURES.md differentiator: "AI self-view (structured feedback)"
- Architecture component: tool call classification

**Avoids:**
- Pitfall #9 (stale fewshot) via minimal behavior-focused examples
- Pitfall #11 (exposing internal state) via curated summary in cross-AI view

**Research flag:** Novel classification logic. AST-based import detection straightforward but needs test coverage. Standard implementation, no research needed.

---

### Phase 5: AI Prompt Refinement (Empirical)

**Rationale:** Prompt changes are behavioral, not structural. Test empirically after infrastructure is in place. Iterate based on observed AI response quality with real usage.

**Delivers:**
- Updated ai_prompt.md with tool conventions section
- "1 fence per response" guidance for cleaner feedback
- Response structure recommendations
- Empirical testing against UAT cases
- Iteration based on AI behavior

**Addresses:**
- FEATURES.md context: ensuring prompt hardening doesn't break helpful code generation
- Architecture component: structured response patterns for cleaner parsing

**Avoids:**
- Pitfall #2 (over-constraining) via positive framing and iterative testing

**Research flag:** Behavioral tuning. Requires empirical observation. Not suitable for upfront research; handle iteratively during execution.

---

### Phase Ordering Rationale

- **Phases 1 and 2 are parallel-safe** — prompt hardening has zero code dependencies, framework refactor doesn't touch AI logic. Could execute concurrently if resources available.
- **Phase 3 depends on Phase 2** — UserView needs formatter infrastructure. Building framework first prevents display code rewrites.
- **Phase 4 depends on Phase 2, independent of Phase 3** — Classification uses formatter metadata, doesn't care about Panel rendering.
- **Phase 5 is empirical** — Needs working system to observe AI behavior. Must come after Phases 1-4 are integrated.
- **Critical path: 2 -> 3** — Framework enables framing. Longest dependency chain.
- **Highest value: 1, 3** — Fix visible defects (hallucinated tools, redundant output). Deliver these first for immediate user benefit.

### Research Flags

**Phases needing deeper research:** None. All patterns are standard or directly documented:
- Prompt hardening: Anthropic multishot guide (official)
- Tool interception: Regex on known XML patterns (langchain-aws issue #521)
- View framework: Strategy pattern + existing ANSI bridge
- Rich rendering: Panel/Syntax API documented, tested locally
- Classification: Pure function, AST stdlib usage

**Phases with standard patterns:**
- **All phases** — Every component builds on proven primitives (Rich, prompt_toolkit, stdlib) or documented patterns (fewshot, strategy, metadata-driven rendering). No novel integration requiring dedicated research-phase.

**Validation during planning:**
- Phase 2 (view framework) may need planning review to verify formatter interface accommodates all view types before building concrete formatters.
- Phase 5 (prompt refinement) is inherently empirical; planning should define testing criteria (which UAT cases must pass) not prescriptive prompt text.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All imports verified against installed packages via runtime check. Rich Panel/Syntax/Group tested locally. ANSI bridge proven in production (channels.py). No new dependencies needed. |
| Features | HIGH | Table stakes derived from v4.0 UAT failures (first-party evidence). Differentiators based on existing channel/router architecture. Anti-features grounded in scope constraints (streaming = API migration, bash = security). |
| Architecture | HIGH | Direct codebase analysis of channels.py, ai.py, shell.py. Formatter pattern fits existing design (Channel already has visibility, markdown, color swappable attributes). Rich-to-prompt_toolkit bridge exists and works. |
| Pitfalls | HIGH | 7 of 12 pitfalls have first-party evidence from v4.0 UAT failures or codebase analysis. ANSI contamination, patch_stdout bypass, width desync documented in Rich/prompt_toolkit issue trackers. Over-constraining grounded in v4.0 prompt calibration history. |

**Overall confidence:** HIGH

All research grounded in official documentation (Anthropic, Rich, prompt_toolkit), verified codebase patterns (channels.py render_markdown, AI eval loop), or first-party failure evidence (v4.0 UAT-2 tests 2 and 5). No speculative designs or unproven integrations.

### Gaps to Address

**Prompt hardening calibration:** Exact wording of no-tools constraint and fewshot examples requires empirical tuning. Research provides pattern (Anthropic multishot guide), but specific text must be validated against AI behavior. Handle iteratively in Phase 5 with defined test criteria (UAT-2 tests 1, 2, 5 must all pass).

**View formatter interface completeness:** Research proposes `render(channel_name, color, content, metadata)` signature. During Phase 2 planning, verify this accommodates all known view types (user, debug, raw, AI-self). If AISelfView needs conversation history context beyond single write, interface may need session reference. Resolve in planning review before building concrete formatters.

**Tool call regex false positives:** TOOL_CALL_RE pattern tested against 4 input cases but not exhaustive AI output corpus. Research provides structural matching strategy (require full `<invoke name="...">` envelope, exclude code fences). Phase 1 execution should include comprehensive fixture testing (XML in docstrings, HTML processing code, Rich markup) before declaring regex production-ready.

**Cross-AI view curation:** Research identifies anti-pitfall #11 (don't expose raw internal state to receiving AI). Cross-AI view mentioned in multi-view concept but not spec'd in detail. If v5.0 includes cross-session memory, define curated summary format during Phase 4 planning. If deferred to v6.0, document explicitly in anti-features.

## Sources

### Primary (HIGH confidence)
- **Codebase analysis:** bae/repl/channels.py (render_markdown ANSI bridge, Channel._display), bae/repl/ai.py (eval loop, _send CLI flags, extract_code), bae/repl/ai_prompt.md (current prompt), .planning/phases/20-ai-eval-loop/20-UAT-2.md (v4.0 failure evidence)
- **Anthropic official:** [Multishot prompting guide](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/multishot-prompting) (fewshot technique), [Reduce hallucinations](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations) (constraint calibration)
- **Rich library:** [Panel docs](https://rich.readthedocs.io/en/stable/panel.html), [Syntax docs](https://rich.readthedocs.io/en/stable/syntax.html), [Group docs](https://rich.readthedocs.io/en/stable/group.html), [Console API](https://rich.readthedocs.io/en/stable/console.html) (StringIO capture), [FAQ](https://github.com/textualize/rich/blob/master/FAQ.md) (ANSI contamination warning)
- **Claude CLI:** [CLI reference](https://code.claude.com/docs/en/cli-reference) (--tools "", --strict-mcp-config, --output-format flags)
- **Local testing:** Rich 14.3.2 Panel/Syntax rendering verified via uv run execution (code + output grouping, 1133 chars ANSI output)

### Secondary (MEDIUM confidence)
- **prompt_toolkit:** [Issue #1346](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1346) (patch_stdout behavior with Rich), [ANSI class reference](https://python-prompt-toolkit.readthedocs.io/en/master/pages/reference.html)
- **Rich integration:** [Discussions #936](https://github.com/Textualize/rich/discussions/936) (Rich+prompt_toolkit pattern), [Issue #3349](https://github.com/Textualize/rich/issues/3349) (ANSI escape width calculations), [Discussions #2648](https://github.com/Textualize/rich/discussions/2648) (ANSI bridge pattern)
- **Tool call format:** [langchain-aws #521](https://github.com/langchain-ai/langchain-aws/issues/521) (Claude XML tool call patterns: function_calls, invoke, antml_invoke)
- **LLM feedback loops:** [EmergentMind research](https://www.emergentmind.com/topics/llm-driven-feedback-loops), [LLMLOOP paper](https://valerio-terragni.github.io/assets/pdf/ravi-icsme-2025.pdf) (correction amplification)

### Tertiary (inference from codebase)
- **v4.0 calibration history:** .planning/phases/20-ai-eval-loop/20-04-PLAN.md (prompt rewrite from "always code" to "code when needed" balance), 20-UAT.md (tests 1, 3, 6 runaway eval loop)
- **Metadata-driven rendering:** Existing code uses metadata["type"] in channels.py for label construction — view framework extends this pattern
- **Strategy pattern fitness:** Channel already has swappable attributes (visible, markdown, color) — formatter follows existing design

---
*Research completed: 2026-02-14*
*Ready for roadmap: yes*
