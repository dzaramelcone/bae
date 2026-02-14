# Domain Pitfalls

**Domain:** Multi-view stream framework, AI prompt hardening, tool call interception, execution display -- added to existing prompt_toolkit + Rich REPL
**Researched:** 2026-02-14
**Confidence:** HIGH -- based on direct codebase analysis, v4.0 UAT failure evidence, and verified Rich/prompt_toolkit behavior

---

## Critical Pitfalls

Mistakes that cause rewrites or major regressions in the core REPL experience.

---

### Pitfall 1: ANSI Escape Contamination in Nested Rich Rendering

**What goes wrong:** Wrapping AI markdown responses in Rich `Panel()` produces broken box-drawing characters. The current `render_markdown()` in channels.py renders Markdown to an ANSI string via `Console(file=StringIO(), force_terminal=True)`, then passes that ANSI string to `print_formatted_text(ANSI(ansi_text))`. If a Panel is added around the Markdown, the ANSI escape sequences from the inner Markdown render corrupt the Panel's width calculations. Box borders misalign, content overflows, and the terminal output becomes unreadable.

**Why it happens:** Rich's Panel calculates content width by counting visible characters. When the content is already ANSI-escaped (from a prior render pass), the invisible escape codes are counted as characters, inflating the width. This is documented in [Rich issue #3349](https://github.com/Textualize/rich/issues/3349) and the [Rich FAQ](https://github.com/textualize/rich/blob/master/FAQ.md). The current architecture does TWO render passes (Rich Markdown -> ANSI string -> prompt_toolkit ANSI). Adding a Panel means either: (a) Panel wraps raw Markdown in Rich's object tree (correct), or (b) Panel wraps the ANSI string output (broken).

**Consequences:** Every AI response renders with garbled borders. Terminal state corruption that persists until clear. Users see mangled output on every AI interaction -- the most visible regression possible.

**Prevention:** The Panel MUST wrap the Markdown object in Rich's renderable tree, NOT the ANSI string output. The render pipeline should be: `Panel(Markdown(text))` -> single `Console.print()` call -> one ANSI string -> `print_formatted_text(ANSI(...))`. Never nest pre-rendered ANSI inside a Rich renderable. Specifically in the current architecture:

```python
# WRONG: Two render passes
md_ansi = render_markdown(text)
panel_ansi = render_panel(md_ansi)  # Broken -- ANSI inside Panel

# RIGHT: Single render pass with composed renderables
buf = StringIO()
console = Console(file=buf, width=width, force_terminal=True)
console.print(Panel(Markdown(text), title="ai:1"))
ansi_output = buf.getvalue()
print_formatted_text(ANSI(ansi_output))
```

If content arriving at the formatter already contains ANSI escapes (e.g. from another Rich render), use `Text.from_ansi()` to convert it into a Rich Text object before wrapping in Panel.

**Detection:** Visual inspection of any Panel-wrapped output. If border characters appear mid-content or the right border is misplaced, this pitfall has been hit. Automated: compare `len(Text.from_ansi(output))` against expected width.

**Phase relevance:** Execution display framing. This is the FIRST thing to validate before writing any Panel rendering code.

---

### Pitfall 2: Over-Constraining AI Prompt Kills Good Behaviors

**What goes wrong:** Adding explicit "you have NO tools" and "NEVER generate XML" constraints causes the AI to become overly cautious, refusing to write code when code is actually needed, or producing stilted/formulaic responses. The v4.0 prompt rewrite already had this dynamic: the original prompt forced code on every turn (bad), the fix swung toward "answer naturally by default" (better), but the next iteration risks over-correcting into "avoid code at all costs."

**Why it happens:** LLMs are sensitive to emphasis. A system prompt with many NEVER/MUST NOT constraints shifts the model's distribution toward compliance with prohibitions rather than helpfulness. The model internalizes "I should avoid doing things" rather than "I should do the right thing." This is documented in [Anthropic's reduce hallucinations guide](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations) -- overly strict constraints can reduce output quality.

Evidence from this codebase: The v4.0 UAT-1 (20-UAT.md) showed that the original prompt's "Use python fences for tool calls. 1 fence per turn" caused runaway code generation across tests 1, 3, and 6. The fix (20-04-PLAN.md) replaced it with "When to write code" criteria with explicit NL-only examples. Adding more constraints on top of this already-calibrated prompt risks breaking the balance that was carefully achieved.

**Consequences:** AI stops writing code for legitimate inspection/computation. Users ask "what variables do I have?" and get "I would need to check the namespace for you" instead of a `ns()` code block. The eval loop becomes useless because the AI never triggers it. Worse: the regression is subtle -- the AI "works" but is unhelpful.

**Prevention:**
1. Frame constraints as WHAT TO DO, not WHAT NOT TO DO. "Use Python code fences for computation and inspection" is better than "NEVER use tool XML."
2. Keep the existing "When to write code" section from the current ai_prompt.md as the anchor. Add tool-rejection as a SPECIFIC case, not a blanket prohibition.
3. Test with the EXACT prompts from UAT-2 test cases: "what's 2**100?" (should produce code), "what variables do I have?" (should produce ns()), "explain what Dep does" (should answer naturally). If any of these regresses, the prompt is over-constrained.
4. Fewshot examples of tool-call rejection should show the AI CORRECTING ITSELF, not refusing to act: "I was about to search for files, but I should use the Python namespace instead:" followed by a code block. This preserves the helpful intent while redirecting the method.

**Detection:** Run the existing UAT-2 test suite (20-UAT-2.md tests 1, 2, 5) after prompt changes. Test 1 (natural NL) and Test 2 (code when appropriate) must BOTH pass. If either regresses, the prompt is miscalibrated.

---

### Pitfall 3: Multi-View Abstraction Breaks Existing Channel Display

**What goes wrong:** Introducing a "view" layer between channels and display breaks the existing working behavior where `channel.write()` immediately renders to terminal. The abstraction intercepts the `_display()` call, adds formatting logic, and introduces new failure modes: blank output, double-rendering, or lost content when the view layer has a bug.

**Why it happens:** The current Channel._display() method is simple and direct (channels.py:76-99):
- Non-markdown: `print_formatted_text(FormattedText([label, content]))` -- one call, immediate output
- Markdown: `print_formatted_text(label)` + `print_formatted_text(ANSI(render_markdown(text)))` -- two calls, immediate output

It also supports metadata-driven labels (`[ai:1]` vs `[ai]`) added in the v4.0 gap closure (20-05-PLAN.md). A view layer must intercept this without breaking either path. The temptation is to replace `_display()` with a configurable formatter, but this means:
- The formatter might not handle all metadata combinations (label, type, mode)
- The formatter might buffer when it should stream
- The formatter might apply Rich Panel/Group to non-markdown channels (breaking line-by-line prefix rendering)
- Tests mock `print_formatted_text` -- a new indirection layer breaks those mocks

**Consequences:** Existing channel output disappears or renders incorrectly. The 245 REPL tests that verify channel output may break. The entire display pipeline becomes untestable because the indirection layer makes mocking harder.

**Prevention:**
1. The view layer MUST be opt-in per channel, not a wholesale replacement. Default view = current behavior exactly.
2. Implement as a `formatter` callable attribute on Channel, defaulting to `None` (use current `_display()`). When set, the formatter receives `(content, metadata)` and handles rendering. When not set, the existing code path executes unchanged.
3. Do NOT change the `_display()` method signature or behavior. Add a new code path: `if self.formatter: self.formatter(content, metadata) else: self._display(content, metadata=metadata)`.
4. Test the default (no formatter) path first. Verify zero test failures with the formatter infrastructure added but unused. Then test each custom formatter independently.
5. The multi-view concept (user view, AI-self view, cross-AI view, debug view) should be DIFFERENT FORMATTERS on the SAME channel data, not different channels or a routing layer. Channel multiplexing already works. Views are presentation, not routing.

**Detection:** Run `uv run python -m pytest tests/repl/ -q` after any change to channels.py. If any test breaks, the view layer has regressed existing behavior. Zero tolerance for existing test failures.

---

### Pitfall 4: Tool Call Interception Regex Matches Normal Code

**What goes wrong:** A regex designed to catch `<tool_use>`, `<invoke>`, `<invoke>`, or similar XML patterns in AI responses also matches legitimate code output. For example, if the AI writes Python code containing XML parsing, HTML templates, or even string literals with angle brackets, the interception fires a false positive. The AI's code is rejected as a "tool call" and corrective feedback is injected, confusing the model and breaking the eval loop.

**Why it happens:** XML-like patterns appear in many legitimate programming contexts:
- Python f-strings: `f"<div class={cls}>"`
- HTML/XML processing: `ET.fromstring("<root><child/></root>")`
- Rich markup: `"[bold]<important>[/bold]"`
- Docstrings explaining API responses: `"Returns <tool_result>...</tool_result>"`
- The AI explaining its own constraints: "I should not use `<tool_use>` blocks"
- The AI quoting this system prompt back: discussing `<invoke name="Grep">` etc.

The v4.0 UAT-2 test 2 already documented the tool hallucination problem: "AI generates fake <tool_use> XML with fabricated file paths and invented results." The fix needs to catch these WITHOUT catching the legitimate cases above.

**Consequences:** False positive interception injects corrective feedback ("You don't have tools, use Python instead") into the conversation. The AI sees this feedback and tries to comply, but it already WAS using Python. This creates the exact feedback loop pathology documented in [LLM feedback loop research](https://www.emergentmind.com/topics/llm-driven-feedback-loops) -- correction causes confusion causes more correction.

**Prevention:**
1. Only scan for tool-use XML OUTSIDE of code fences. The AI's code blocks (` ```python ... ``` `) should be excluded from interception. Extract code blocks first (using the existing `_CODE_BLOCK_RE` from ai.py), then scan the remaining text.
2. Use a STRUCTURAL pattern, not a keyword pattern. Match the full tool-use envelope: `<invoke name="[^"]+">` with nested `<parameter>` tags, or `<tool_use>` with a `<tool_name>` child. Require the STRUCTURE, not just the tag name.
3. Require the XML to appear at the response's top level (not inside inline code, not inside a quoted block). A simple heuristic: the tool-use XML must start at column 0 or after only whitespace.
4. Consider the simplest reliable detector: does the response contain a complete `<invoke name="...">...</invoke>` block that is NOT inside a code fence? If yes, intercept. If partially formed or inside a fence, ignore.
5. If the response contains BOTH a tool-use XML block AND a Python code fence, trust the code fence and strip the XML. The model is hedging; the code fence is the useful output.

**Detection:** Unit test with responses containing:
- Legitimate code with XML processing (must NOT trigger)
- AI explaining that it doesn't have tools, mentioning tool_use in prose (must NOT trigger)
- Actual hallucinated tool calls with full invoke structure (MUST trigger)
- Mixed: code fence + tool XML in same response (should strip XML, keep code)
- Partial/incomplete XML fragments (must NOT trigger)
If legitimate code triggers interception, the regex is too broad.

---

## Moderate Pitfalls

---

### Pitfall 5: Execution Display Deduplication Removes Useful Information

**What goes wrong:** The v4.0 UAT-2 test 5 identified that eval loop output appears redundantly: code appears in the AI's markdown response (as a code block), and again on the `[py]` channel with `ai_exec` type. The natural fix is deduplication -- suppress the `[py]` channel output. But this removes the ONLY place where execution OUTPUT (not code) is visible to the user. The AI's markdown shows the CODE it wrote; the `[py:ai_exec_result]` tee shows the RESULT of running it. Suppressing all `[py]` output means users cannot see execution results.

**What actually needs deduplication:** The CODE input appears twice (in AI markdown response and on `[py]` with type `ai_exec`). The RESULT appears once (on `[py]` with type `ai_exec_result`). Deduplication should suppress the CODE echo on `[py]`, not the result. The metadata `type` field already distinguishes these -- `ai_exec` vs `ai_exec_result`.

**Prevention:**
1. In the user-facing view, suppress `[py]` writes with `metadata.type == "ai_exec"` (these are duplicated code). Display `[py]` writes with `metadata.type == "ai_exec_result"` (these are unique results).
2. The execution display frame should show: `[result]` only, not `[full code] -> [result]`. The code is already visible in the AI's markdown response.
3. Store both `ai_exec` and `ai_exec_result` in the session store regardless of display suppression -- the AI feedback loop and cross-session memory still need both. Display filtering is a view concern, not a storage concern.
4. The AI-self view (what the model sees in feedback) should still include both code and output -- the model needs the full context. Only the user-facing view is deduplicated.

**Detection:** After implementation, verify: (a) user sees execution results but not duplicated code, (b) `store.search("ai_exec")` returns both code and results, (c) AI feedback still includes full code+output context.

---

### Pitfall 6: Terminal Width Desynchronization with Rich Panel Rendering

**What goes wrong:** The `render_markdown()` function captures terminal width at render time via `os.get_terminal_size().columns`. If Panel rendering adds a border (2 characters for left+right box drawing) and padding (2+ characters), the effective content width is `terminal_width - 4` minimum. If the Markdown was rendered assuming full terminal width and then wrapped in a Panel post-hoc, it overflows the Panel's right border.

**Why it happens:** Rich handles width subtraction for borders/padding internally when you compose renderables in a single render pass (`Console.print(Panel(Markdown(text)))`). But if the architecture renders Markdown separately and then wraps the result in a Panel, the width budget is spent twice.

Additionally, terminal resize during output (user drags window while AI is responding) causes mid-render width changes. tmux/screen sessions report different widths than the actual display. SSH sessions with different local/remote terminal sizes cause mismatches.

**Prevention:**
1. When rendering Panel(Markdown(...)), pass `width=terminal_width` to the Console, NOT to the inner Markdown. Rich handles the internal width subtraction for Panel borders/padding.
2. Always use a single `Console.print(composed_renderable)` call. Never pre-render inner content and then wrap it.
3. For testing, always use explicit width: `Console(file=StringIO(), width=80, force_terminal=True)`. No terminal dependency in tests.
4. Use Rich's overflow control: `Panel(Markdown(text), expand=False)` for tight-fitting panels, or set explicit `width` on the Panel for fixed-width output.

**Detection:** Test with `width=40` (narrow terminal). If Panel borders wrap to the next line, width calculation is wrong. Test with `width=200` (wide terminal). If content has unnecessary whitespace, the Panel is expanding when it should not.

---

### Pitfall 7: Feedback Loop Amplification in Tool Call Correction

**What goes wrong:** When the interception layer detects a hallucinated tool call and injects corrective feedback ("You don't have tools, use Python instead"), the AI receives this as its next prompt in the eval loop. This counts as one eval iteration. The AI then generates a new response -- but Claude CLI is trained for tool use, so it may generate ANOTHER tool call. The interception fires again. This consumes all `max_eval_iters` (currently 5) without producing useful output.

**Why it happens:** The eval loop in `AI.__call__` (ai.py:93-124) is designed for code extraction and execution feedback. Tool call interception adds a second purpose (behavioral correction). These conflict: the code extraction loop expects each iteration to produce code that runs and generates output, while the correction loop expects each iteration to produce a "better" response. If the model doesn't converge (keeps generating tool XML despite correction), the loop exhausts with zero useful work.

This is the same category of issue as the v4.0 runaway eval loop (20-UAT.md gap 1) where prompt miscalibration caused every response to generate code blocks. Tool call correction creates the same dynamic: every response triggers intervention, intervention triggers a new response, which triggers more intervention.

**Prevention:**
1. Tool call correction should happen ONCE per `__call__` invocation, not per eval iteration. After one correction, if the model still generates tool XML, strip the XML and present the remaining text as the response. Do not re-prompt.
2. Track correction count separately from eval iteration count. Suggested: `max_corrections = 1`. If the first correction fails to change behavior, the model won't converge regardless of how many times you try.
3. The corrective prompt should be SPECIFIC: include the exact tool name that was rejected and what to do instead. "You tried to use Grep, but you don't have external tools. Search the namespace using Python: `store.search('term')` or `ns()`." Generic "don't use tools" repeats what the system prompt already says.
4. Consider whether correction should happen at the `_send()` level (before the response reaches the eval loop) rather than inside the eval loop. This avoids consuming eval iterations on correction.

**Detection:** Log how many eval iterations are consumed by corrections vs. actual code execution. If `max_eval_iters` is routinely exhausted with zero code blocks executed, the correction loop is failing to converge.

---

### Pitfall 8: View Formatter Bypasses prompt_toolkit's patch_stdout

**What goes wrong:** The REPL runs inside `patch_stdout()` context manager (shell.py:422), which redirects all stdout writes through prompt_toolkit to avoid corrupting the prompt display. If a view formatter creates its own Rich Console writing to `sys.stdout` directly (instead of a StringIO buffer), the output bypasses `patch_stdout()` and corrupts the prompt. Characters appear inside the input area, the cursor jumps, and the terminal state becomes inconsistent.

**Why it happens:** The current `render_markdown()` correctly uses `Console(file=StringIO())` -- it never touches stdout. But a new formatter might create `Console()` with default `file=None` (which means stdout), especially if copying patterns from Rich documentation examples that assume direct terminal output. Every Rich tutorial starts with `console = Console()` followed by `console.print(...)` -- this writes to stdout directly.

**Prevention:**
1. ALL Rich rendering in the view layer MUST go through `Console(file=StringIO())`, never `Console()` with default stdout.
2. The final output MUST go through `print_formatted_text()` from prompt_toolkit, which is patch_stdout-safe.
3. Create a factory function used by all formatters:
```python
def _make_console(width: int | None = None) -> Console:
    """Console for rendering Rich objects to ANSI string. Never writes to stdout."""
    if width is None:
        try:
            width = os.get_terminal_size().columns
        except OSError:
            width = 80
    return Console(file=StringIO(), width=width, force_terminal=True)
```
4. Add a code comment at the top of any new formatter module: "All Rich Console instances MUST use file=StringIO(). Direct stdout writes corrupt prompt_toolkit's display."

**Detection:** If text appears garbled around the prompt input area, or the cursor position is wrong after AI output, a formatter is writing to stdout directly. Test by running a long AI response while typing at the prompt -- if the input line is corrupted, stdout is being written directly.

---

## Minor Pitfalls

---

### Pitfall 9: Fewshot Examples in System Prompt Become Stale

**What goes wrong:** Adding fewshot examples of tool-call rejection to the AI system prompt creates a maintenance burden. If the tool-use XML format changes (Anthropic updates their schema, Claude Code updates its internal envelope format), the fewshot examples show the wrong patterns. The AI then learns to reject the EXAMPLES' format but not the actual format it encounters in practice.

**Prevention:** Keep fewshot examples minimal (1-2 cases). Focus on the BEHAVIOR pattern (detect-reject-redirect), not the exact XML syntax. Use a generic marker like `<tool_use>` rather than specific namespaced tags (`<invoke>`) which may change between Claude versions. The examples should demonstrate the CORRECTION pattern, not catalog every possible tool format.

### Pitfall 10: Debug View Toggle Adds Global State

**What goes wrong:** A debug mode toggle ("show raw channel data instead of formatted") adds boolean state that must be checked on every write. If the toggle is implemented as a global flag rather than a per-channel formatter swap, it creates an implicit dependency that's easy to forget when adding new display code paths.

**Prevention:** Debug view should be a formatter, not a flag. `channel.formatter = debug_formatter` enables it, `channel.formatter = None` returns to default. No globals, no if-statements scattered across the display hot path. The existing `enable_debug(router)` / `disable_debug(router)` pattern for file logging (channels.py:158-174) shows the right approach -- attach/detach a handler, don't flip a global.

### Pitfall 11: Cross-AI View Exposes Internal Conversation State

**What goes wrong:** The multi-view concept includes a view showing what one AI session sees of another's work. If this view simply dumps raw channel data between sessions, it may expose session IDs, internal metadata, error traces, and prompt engineering artifacts that confuse the receiving AI rather than helping it.

**Prevention:** Cross-AI view should be a curated summary, not raw data. Use the same `_build_context()` pattern from ai.py (lines 215-277) -- structured, truncated, formatted as Python REPL output. The receiving AI should see "Session 2 defined class Weather with fields temp, humidity" not the raw channel log of session 2's conversation turns.

### Pitfall 12: Execution Display Frame Renders Empty For Code-Only Responses

**What goes wrong:** If the execution display uses a Rich Panel to frame code+output, and a code block produces no output (e.g., `x = 42` -- pure assignment), the Panel renders with empty content inside a border. This looks broken: a decorated frame with nothing inside it.

**Prevention:** Only render the execution display frame when there IS output to display. Pure assignments and side-effect-free statements should NOT produce a visible frame. Check: if `ai_exec_result` content is empty or "(no output)", skip the framed display entirely.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Multi-view framework | #3 (breaking existing display), #8 (patch_stdout bypass), #10 (global debug state) | Implement as opt-in formatter on Channel, test default path first, enforce StringIO console factory, use formatter swap not flag |
| AI prompt hardening | #2 (over-constraining), #9 (stale fewshot) | Frame as positive guidance not prohibitions, test with existing UAT prompts, keep fewshot minimal and behavior-focused |
| Tool call interception | #4 (false positive regex), #7 (correction feedback loop) | Exclude code fences from scanning, require structural XML match, limit correction to 1 attempt per call |
| Execution display | #1 (ANSI contamination in Panel), #5 (deduplication removing results), #6 (width desync), #12 (empty frames) | Single Rich render pass with composed renderables, deduplicate code echo not results, let Console handle width, skip frame on empty output |

---

## Evidence Base

| Finding | Source | Confidence |
|---------|--------|------------|
| ANSI escape sequences break Panel alignment | [Rich #3349](https://github.com/Textualize/rich/issues/3349), [Rich FAQ](https://github.com/textualize/rich/blob/master/FAQ.md) | HIGH |
| Rich Console with StringIO is the correct prompt_toolkit integration | [prompt-toolkit #1346](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1346), [Rich discussions #936](https://github.com/Textualize/rich/discussions/936), current channels.py render_markdown() | HIGH |
| Over-constraining prompts reduces quality | [Anthropic hallucination guide](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations), [Claude prompt best practices](https://claude.com/blog/best-practices-for-prompt-engineering) | HIGH |
| Feedback loops amplify errors in LLM code correction | [LLM feedback loop research](https://www.emergentmind.com/topics/llm-driven-feedback-loops), [LLMLOOP paper](https://valerio-terragni.github.io/assets/pdf/ravi-icsme-2025.pdf) | MEDIUM |
| AI tool hallucination already observed in this codebase | v4.0 UAT-2 test 2 (20-UAT-2.md): "AI generates fake <tool_use> XML with fabricated file paths" | HIGH -- first-party evidence |
| Code display duplication already observed | v4.0 UAT-2 test 5 (20-UAT-2.md): "Output tee works but code appears 2-3x" | HIGH -- first-party evidence |
| Runaway eval loop from prompt miscalibration | v4.0 UAT-1 tests 1, 3, 6 (20-UAT.md), root cause in 20-04-PLAN.md | HIGH -- first-party evidence |
| Prompt rewrite balance is fragile | v4.0 20-04-PLAN.md: prompt went from "always code" to "code only when needed" -- the current calibration works for 4/6 tests | HIGH -- first-party evidence |
| Rich Markdown code_theme and Panel width handled internally | [Rich Markdown docs](https://rich.readthedocs.io/en/latest/markdown.html), [Rich Panel docs](https://rich.readthedocs.io/en/stable/reference/panel.html) | HIGH |
| Claude CLI --tools "" disables tool use | Current ai.py _send() line 138: `"--tools", ""` already used | HIGH -- in codebase |
| Claude CLI --strict-mcp-config + --setting-sources "" | Current ai.py _send() lines 139-140: already disabling external tools/settings | HIGH -- in codebase |

---
*Pitfalls researched: 2026-02-14 for v5.0 Stream Views milestone*
*Previous version: v4.0 Cortex pitfalls (2026-02-13) -- archived, pitfalls 1-15 from that version are now resolved or not applicable to v5.0 scope*
