# Phase 21: Execution Convention - Research

**Researched:** 2026-02-14
**Domain:** LLM output convention design, regex-based code extraction, multi-model eval harness
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Marking convention
- Convention choice is an **open research question** -- must be empirically validated
- Test all three candidates equally: fence annotation (`python:exec`), wrapper marker (`<exec>`), and inverse convention (mark examples instead)
- Run evals across **Opus, Sonnet, and Haiku** -- convention must work across all Claude tiers
- Eval uses simple, straightforward prompts and fewshot with fake conversation samples -- no adversarial testing
- **100% compliance required** under normal conditions -- if a convention fails on any model with reasonable prompts, it's rejected
- The winning convention is whatever the evals select

#### Multi-block handling
- **One executable block per response** -- only the first block marked as executable is extracted and run
- Additional executable blocks are ignored
- AI receives feedback: "Only your first executable block was run. N additional blocks were ignored."
- User also sees a notice that extra blocks were ignored

#### Backward compatibility
- **No backward compatibility** -- clean break from current `extract_code()` behavior
- Convention applies to **all AI responses**, not just eval loop turns
- No fallback mode for models that don't follow the convention -- if convention isn't used, no code executes
- No config toggle -- convention is required
- `extract_code()` is **fully replaced** by the new convention-aware extractor
- Entire design is driven by eval results

### Claude's Discretion
- Fallback behavior when AI doesn't use the convention (Claude decides based on eval data whether to run nothing or apply a heuristic)
- Exact eval harness design and prompt scenarios
- How to present the "blocks ignored" notice to the user (channel, styling)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

## Summary

Phase 21 replaces the current `extract_code()` function (which blindly extracts all Python code fences from AI responses) with a convention-aware extractor that only executes code the AI explicitly marks as executable. This prevents illustrative code (examples, pseudocode, explanations) from being accidentally executed in the eval loop.

The core challenge is empirical: three candidate marking conventions must be tested across Opus, Sonnet, and Haiku to determine which one the models follow with 100% compliance under normal prompting conditions. The eval harness uses the existing Claude CLI subprocess pattern already in the codebase (`AI._send`-style invocation) to dispatch test prompts to each model and validate that responses use the convention correctly.

The implementation is small in code terms -- a new regex, a new extraction function, updated system prompt, and the eval harness -- but the eval results drive every design decision. If a convention gets 100% on all three tiers, it wins. If none do, the eval data informs fallback strategy.

**Primary recommendation:** Build the eval harness first, run it, let the data pick the convention, then implement the winner as a regex-based extractor replacing `extract_code()`. The harness is a standalone pytest-based script (or marked `e2e`) that dispatches prompts to Claude CLI and validates response formatting.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| re (stdlib) | N/A | Regex-based code extraction from AI responses | Already used for current `_CODE_BLOCK_RE`. No new deps. |
| asyncio (stdlib) | N/A | Subprocess management for eval harness | Already used throughout the codebase |
| pytest | >=8.0 | Eval harness structure and assertions | Already a dev dependency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | | | Zero new dependencies per prior decision |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Claude CLI subprocess for eval | Anthropic SDK directly | Would add API key requirement. CLI is already in use, zero-config. Eval should use the same interface production uses. |
| pytest for eval harness | Custom script | pytest provides markers, fixtures, parametrize, and output formatting. Already in dev deps. |

## Architecture Patterns

### File Structure
```
bae/repl/
    ai.py              # Replace extract_code() with convention-aware extractor
    ai_prompt.md        # Add fewshot examples showing convention usage
tests/repl/
    test_ai.py          # Update TestExtractCode for new convention
evals/                  # NEW directory for eval harness
    conftest.py         # Shared fixtures (model list, prompt templates)
    test_convention.py  # Parametrized eval: convention x model x scenario
```

### Pattern 1: Convention Candidates (Regex Design)

All three candidates and their extraction regex patterns:

#### Candidate A: Fence annotation (`python:exec`)

AI writes ````python:exec` instead of ````python` for executable code.

```markdown
Here's how to use the function:
```python
# This is just an example
x = do_something()
```

Let me run it for you:
```python:exec
result = do_something()
```
```

**Regex:**
```python
# Extracts content of ```python:exec fences only
_EXEC_BLOCK_RE = re.compile(
    r"```python:exec\s*\n(.*?)\n```",
    re.DOTALL,
)
```

**Pros:** Minimal change to current markdown. Models already understand fence annotations (```json, ```typescript, etc.). Natural extension of markdown convention. Visually distinct.
**Cons:** Novel annotation -- no model has been trained on `python:exec` specifically. Must be taught entirely through fewshot.

#### Candidate B: Wrapper marker (`<exec>`)

AI wraps executable code blocks in `<exec>` tags.

```markdown
Here's how to use the function:
```python
# This is just an example
x = do_something()
```

Let me run it for you:
<exec>
```python
result = do_something()
```
</exec>
```

**Regex:**
```python
# Extracts Python fence content that appears inside <exec> tags
_EXEC_BLOCK_RE = re.compile(
    r"<exec>\s*```(?:python|py)?\s*\n(.*?)\n```\s*</exec>",
    re.DOTALL,
)
```

**Pros:** XML tags are deeply familiar to Claude -- system prompts, tool definitions, and artifacts all use them. Claude models are heavily trained to produce structured XML output. Unambiguous parsing.
**Cons:** Visually noisier. Two layers of markup (XML + fence). Slightly more complex regex.

#### Candidate C: Inverse convention (mark examples instead)

By default, all Python fences are executable (preserving current behavior). AI marks illustrative/example code with a different annotation.

```markdown
Here's how to use the function:
```python:example
# This is just an example
x = do_something()
```

Let me run it for you:
```python
result = do_something()
```
```

**Regex:**
```python
# Extracts content of all Python fences EXCEPT those annotated as :example
_EXEC_BLOCK_RE = re.compile(
    r"```(?:python|py)(?!:example)\s*\n(.*?)\n```",
    re.DOTALL,
)
```

**Pros:** Smallest change from current behavior -- bare fences still execute. Only need to teach the "example" escape hatch. Gradual adoption path (if AI forgets the convention, code still runs).
**Cons:** Fails silently when convention isn't followed (examples execute). Harder to enforce 100% compliance because the "wrong" behavior looks like the "right" behavior. Potentially undermines the whole point of the phase (preventing accidental execution).

### Pattern 2: Eval Harness Design

The eval harness is a parametrized pytest test that dispatches prompts to each model via Claude CLI and validates that responses follow the convention.

```python
# evals/test_convention.py structure

MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]

CONVENTIONS = ["fence_annotation", "wrapper_marker", "inverse"]

# Each scenario is a (prompt, expected_behavior) pair
SCENARIOS = [
    # Pure NL question -- no code expected
    ("What is a Graph in bae?", "no_code"),
    # Computation request -- one executable block expected
    ("What's 2**100?", "one_exec"),
    # Explain with example -- illustrative code only, no executable
    ("Explain how Dep works with an example", "no_exec"),
    # Inspect namespace -- one executable block expected
    ("What variables do I have?", "one_exec"),
    # Mixed: explain + run -- one illustrative, one executable
    ("Show me how to define a Node and then create one", "mixed"),
]

@pytest.mark.e2e
@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("convention", CONVENTIONS)
@pytest.mark.parametrize("scenario_name,expected", SCENARIOS)
async def test_convention_compliance(model, convention, scenario_name, expected):
    """Dispatch prompt with convention-specific system prompt, validate response."""
    system_prompt = build_system_prompt(convention)
    response = await send_to_claude(model, system_prompt, scenario_name)
    validate_response(response, convention, expected)
```

**Key design decisions:**
- Uses `pytest.mark.e2e` so it doesn't run in normal test suite (matches existing `conftest.py` `--run-e2e` flag)
- Parametrized across model x convention x scenario for full matrix
- Each convention has its own system prompt variant with matching fewshot examples
- `send_to_claude` uses the same Claude CLI subprocess pattern as `AI._send`
- `validate_response` checks regex extraction matches expected behavior

### Pattern 3: System Prompt with Fewshot Convention Examples

The system prompt is the primary teaching mechanism. Based on Anthropic's guidance, 3-5 diverse examples with XML `<example>` tags are the most effective way to get Claude to follow a convention.

```markdown
# Current ai_prompt.md convention section (to be added):

## Code execution convention
Every Python code fence you write is either EXECUTABLE or ILLUSTRATIVE.
- EXECUTABLE: Code that should run in the REPL. Use `python:exec` annotation.
- ILLUSTRATIVE: Examples, pseudocode, explanations. Use plain `python` annotation.

Only your FIRST executable block per response is run. Additional executable blocks are ignored.

<examples>
<example>
User: what's 2**100?
Assistant:
```python:exec
2**100
```
</example>

<example>
User: explain how Dep works with an example
Assistant: Dep is a marker for field-level dependency injection. When a Node field is annotated with Dep(fn), the graph resolves and injects the dependency before the node executes.

Here's what it looks like:
```python
# Illustrative -- how Dep is used in a Node definition
class WeatherNode(Node):
    forecast: Annotated[str, Dep(get_forecast)]
```
</example>

<example>
User: show me my variables and explain what ns() does
Assistant: `ns()` lists all namespace objects with types and summaries. Let me show you:
```python:exec
ns()
```

The function inspects every non-underscore entry in the namespace and prints a formatted table:
```python
# How ns() works internally (illustrative)
for name, obj in sorted(namespace.items()):
    if not name.startswith("_"):
        print(f"{name}  {type(obj).__name__}")
```
</example>
</examples>
```

**Note:** The above example uses Candidate A (fence annotation). Each candidate gets its own prompt variant with matching examples.

### Pattern 4: Convention-Aware Extractor (replaces extract_code)

```python
# In ai.py -- replaces current extract_code()
# Final regex depends on eval winner

class AI:
    @staticmethod
    def extract_executable(text: str) -> tuple[str | None, int]:
        """Extract the first executable code block and count of additional blocks.

        Returns (code, extra_count) where:
        - code is the first executable block content, or None if no executable blocks
        - extra_count is the number of additional executable blocks that were ignored
        """
        matches = _EXEC_BLOCK_RE.findall(text)
        if not matches:
            return None, 0
        return matches[0], len(matches) - 1
```

### Pattern 5: Multi-Block Feedback

When extra executable blocks are ignored, both the AI and the user receive notice.

```python
# In AI.__call__ eval loop:
code, extra = self.extract_executable(response)
if code is None:
    break

# Execute the single block
result, captured = await async_exec(code, self._namespace)
# ... (existing result handling)

# Notify about ignored blocks
if extra > 0:
    ignored_notice = (
        f"Only your first executable block was run. "
        f"{extra} additional block{'s' if extra != 1 else ''} "
        f"{'were' if extra != 1 else 'was'} ignored."
    )
    # Append to AI feedback
    feedback = f"[Output]\n{output}\n\n{ignored_notice}"
    # Show user notice via debug channel (non-intrusive)
    self._router.write(
        "debug", ignored_notice, mode="DEBUG",
        metadata={"type": "exec_notice"},
    )
```

### Anti-Patterns to Avoid

- **Pre-committing to a convention before evals run:** The whole point is empirical validation. Do not build the production extractor first and eval second.
- **Testing with adversarial prompts:** The decision explicitly says "simple, straightforward prompts and fewshot with fake conversation samples -- no adversarial testing." Evals should use realistic, natural prompts.
- **Using the Anthropic SDK for evals:** The production system uses Claude CLI. The eval should use the same interface to test the exact same code path.
- **Overly complex regex:** All three candidates can be extracted with a single regex. Do not build a multi-pass parser.
- **Bare ``` fence support in new extractor:** The current extractor matches bare ``` (no language tag). The new convention should NOT match bare fences -- they are ambiguous and likely illustrative (shell output, config files, etc.).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Code extraction | Multi-pass text parser | Single regex with `re.compile` | All three candidates are cleanly regex-extractable. The current extractor is a one-liner regex. |
| CLI subprocess for eval | Custom HTTP client or SDK wrapper | Existing `asyncio.create_subprocess_exec` pattern from `AI._send` | Same code path as production. Zero new deps. |
| Prompt templating | Jinja or string formatting library | f-strings with multi-line strings | System prompts are static per convention. No dynamic templating needed. |
| Result validation | Custom assertion framework | pytest parametrize + assert | Already in dev deps. Built for exactly this. |

**Key insight:** The entire phase is ~200 lines of production code (new regex, updated `extract_code`, updated prompt, multi-block notice) plus ~300 lines of eval harness. The eval harness is the bulk of the work, and it's throwaway infrastructure -- it runs once, picks the winner, and the production code is trivial.

## Common Pitfalls

### Pitfall 1: Model-specific fewshot sensitivity
**What goes wrong:** A convention works perfectly on Opus (which follows instructions precisely) but fails on Haiku (which may take shortcuts or ignore subtle formatting rules).
**Why it happens:** Haiku has less capacity for following novel conventions. It tends to "complete patterns" rather than "follow rules."
**How to avoid:** The eval explicitly tests all three tiers. Fewshot examples must be crystal clear and consistent. Prefer conventions that feel "natural" rather than "novel" -- Haiku follows patterns better than rules.
**Warning signs:** Haiku producing bare ````python` fences without the exec annotation, or omitting `<exec>` wrapper tags.

### Pitfall 2: Regex false positives on illustrative exec blocks
**What goes wrong:** AI writes `python:exec` in an illustrative example showing the user how the convention itself works.
**Why it happens:** AI is explaining how to use the convention and writes ````python:exec` inside a larger illustrative block.
**How to avoid:** System prompt should explicitly say "never use the exec annotation in illustrative code, even when explaining the convention." Also: nested fences (fence inside fence) are inherently ambiguous in markdown -- regex handles them poorly. Keep fewshot examples simple.
**Warning signs:** Eval tests that ask "explain how the exec convention works" produce false positives.

### Pitfall 3: Claude CLI session contention in eval harness
**What goes wrong:** Parallel eval runs try to use the same Claude CLI session, causing "already in use" errors.
**Why it happens:** The eval harness dispatches many prompts. If run in parallel, session IDs collide.
**How to avoid:** Each eval call uses `--no-session-persistence` (single-shot mode) with no session ID. This is how `ClaudeCLIBackend._run_cli_json` already works. Do NOT use `--session-id` or `--resume` in the eval harness.
**Warning signs:** "already in use" errors in eval output.

### Pitfall 4: Eval harness prompt contamination
**What goes wrong:** The eval prompt accidentally teaches the convention through the question itself, rather than through the system prompt fewshot.
**Why it happens:** Scenario prompts like "Write executable code to compute 2**100" embed the word "executable" which hints at the convention.
**How to avoid:** Scenario prompts should be identical across all three conventions. They should be natural user prompts that don't reference the convention at all. The system prompt (with fewshot) is the only place the convention is taught.
**Warning signs:** All conventions score 100% because the prompt is doing the teaching, not the system prompt.

### Pitfall 5: Inverse convention silent failure
**What goes wrong:** Candidate C (inverse convention) appears to pass all tests because when the AI forgets the convention, illustrative code executes anyway -- and the test doesn't catch it because execution succeeded.
**Why it happens:** The "expected" behavior for inverse convention is harder to validate. A bare ````python` fence with illustrative code is a convention failure, but the extractor treats it as executable.
**How to avoid:** Eval tests for inverse convention must explicitly check that illustrative-only scenarios produce NO executable blocks. The validator must inspect the raw response text, not just whether extraction produced code.
**Warning signs:** Inverse convention getting 100% compliance when the other two don't -- that's suspicious.

### Pitfall 6: Haiku timeout in eval
**What goes wrong:** Haiku is fast but sometimes Claude CLI startup overhead dominates, causing inconsistent timing.
**Why it happens:** Claude CLI has cold start overhead unrelated to model speed.
**How to avoid:** Set generous timeout (30s) for eval calls. Don't fail on timeout -- retry once. The eval cares about convention compliance, not latency.
**Warning signs:** Flaky eval results with Haiku where the same scenario passes/fails on retries.

## Code Examples

### Current extract_code (being replaced)
```python
# Source: bae/repl/ai.py lines 28-31
_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```",
    re.DOTALL,
)

@staticmethod
def extract_code(text: str) -> list[str]:
    """Extract Python code blocks from markdown-fenced text."""
    return _CODE_BLOCK_RE.findall(text)
```

### Candidate A regex (fence annotation)
```python
import re

_EXEC_FENCE_RE = re.compile(
    r"```python:exec\s*\n(.*?)\n```",
    re.DOTALL,
)

def extract_executable(text: str) -> tuple[str | None, int]:
    matches = _EXEC_FENCE_RE.findall(text)
    if not matches:
        return None, 0
    return matches[0], len(matches) - 1
```

### Candidate B regex (wrapper marker)
```python
import re

_EXEC_WRAP_RE = re.compile(
    r"<exec>\s*```(?:python|py)?\s*\n(.*?)\n```\s*</exec>",
    re.DOTALL,
)

def extract_executable(text: str) -> tuple[str | None, int]:
    matches = _EXEC_WRAP_RE.findall(text)
    if not matches:
        return None, 0
    return matches[0], len(matches) - 1
```

### Candidate C regex (inverse convention)
```python
import re

# Match Python fences that do NOT have :example annotation
_EXEC_INVERSE_RE = re.compile(
    r"```(?:python|py)(?!:example)\s*\n(.*?)\n```",
    re.DOTALL,
)

def extract_executable(text: str) -> tuple[str | None, int]:
    matches = _EXEC_INVERSE_RE.findall(text)
    if not matches:
        return None, 0
    return matches[0], len(matches) - 1
```

### Eval harness: sending a prompt to Claude CLI
```python
# Source: pattern from bae/repl/ai.py AI._send, adapted for eval
import asyncio
import os

async def eval_send(model: str, system_prompt: str, user_prompt: str, timeout: int = 30) -> str:
    """Send a single-shot prompt to Claude CLI and return the response."""
    cmd = [
        "claude",
        "-p", user_prompt,
        "--model", model,
        "--output-format", "text",
        "--tools", "",
        "--strict-mcp-config",
        "--setting-sources", "",
        "--no-session-persistence",
        "--system-prompt", system_prompt,
    ]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout_bytes, _ = await asyncio.wait_for(
        process.communicate(), timeout=timeout,
    )
    return stdout_bytes.decode().strip()
```

### Eval harness: validation function
```python
def validate_response(response: str, convention: str, expected: str):
    """Validate that the response follows the convention correctly."""
    # Build the appropriate regex for this convention
    regex = CONVENTION_REGEXES[convention]
    exec_blocks = regex.findall(response)

    # Also extract ALL python fences (for checking illustrative blocks)
    all_python = re.findall(r"```(?:python|py)\S*\s*\n(.*?)\n```", response, re.DOTALL)

    if expected == "no_code":
        # No code blocks at all expected
        assert len(all_python) == 0, f"Expected no code blocks, got {len(all_python)}"
    elif expected == "one_exec":
        # Exactly one executable block, possibly zero illustrative
        assert len(exec_blocks) >= 1, f"Expected executable block, got none"
    elif expected == "no_exec":
        # Illustrative blocks only, zero executable
        assert len(exec_blocks) == 0, f"Expected no executable blocks, got {len(exec_blocks)}"
        assert len(all_python) >= 1, f"Expected illustrative blocks, got none"
    elif expected == "mixed":
        # At least one executable AND at least one non-executable
        assert len(exec_blocks) >= 1, f"Expected executable block, got none"
        assert len(all_python) > len(exec_blocks), (
            f"Expected illustrative blocks beyond exec blocks"
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Run all code fences blindly (current `extract_code`) | Convention-marked executable blocks only | Phase 21 | Prevents accidental execution of examples, pseudocode, explanations |
| Single extraction function returning list[str] | Extraction returning (first_block, extra_count) | Phase 21 | Supports one-block-per-response policy with user/AI feedback |
| No model eval for prompt conventions | Multi-model eval harness with empirical selection | Phase 21 | Data-driven convention choice across Opus/Sonnet/Haiku |

**Relevant prior art:**
- Claude Code itself distinguishes between "thinking" and "tool use" via structured output, not markdown conventions. But Claude Code uses the API with tool definitions, not CLI subprocess. Different problem.
- Jupyter notebooks distinguish code cells from markdown cells via cell type, not fence annotation. Analogous concept but different mechanism.
- GitHub Copilot Chat uses a convention where executable code suggestions are rendered in a specific UI widget, but the LLM doesn't mark them differently -- the IDE does classification. Different architecture.

## Discretionary Recommendations

### Fallback behavior (Claude's discretion)

**Recommendation: Run nothing when convention is not used.**

Rationale: The decision explicitly says "no fallback mode for models that don't follow the convention -- if convention isn't used, no code executes." This is the safest and simplest approach. If the eval reveals that a convention fails on a model tier, the convention is rejected entirely -- we don't need a heuristic fallback for individual responses because the winning convention will have 100% compliance.

The system prompt already includes an instruction "1 fence per turn max. Every fence is immediately executed." We are replacing this with the new convention. If the AI writes bare fences, nothing runs. The AI will notice its code didn't execute in the feedback and self-correct.

### "Blocks ignored" notice presentation (Claude's discretion)

**Recommendation: Use the `debug` channel with a distinct metadata type.**

The debug channel is visible by default and uses a muted gray color (#808080). A notice like "Only the first executable block was run. 2 additional blocks were ignored." is operational information -- not an error, not AI output, not Python output. The debug channel is semantically correct.

Metadata `{"type": "exec_notice"}` distinguishes it from other debug messages for potential future filtering.

### Eval harness structure (Claude's discretion)

**Recommendation: `evals/` directory with pytest e2e marker.**

Place eval tests in `evals/test_convention.py` (new directory), not in `tests/repl/`. Rationale:
1. Evals call real Claude CLI -- they cost money and take time. Not suitable for `pytest` default run.
2. The `--run-e2e` marker already exists in conftest.py.
3. Evals are throwaway -- they run once to pick the winner, then the code is either archived or deleted.

Structure: 3 conventions x 3 models x 5 scenarios = 45 test cases. At ~10s per Claude CLI call, full matrix takes ~8 minutes. Can be parallelized across conventions since they use `--no-session-persistence`.

**Scenario prompt design:**

| # | Prompt | Expected | Tests |
|---|--------|----------|-------|
| 1 | "What is a Graph in bae?" | no_code | Pure NL -- AI should not write any code |
| 2 | "What's 2**100?" | one_exec | Computation -- needs one executable block |
| 3 | "Explain how Dep works with an example" | no_exec | Illustrative only -- explain with code example that should NOT execute |
| 4 | "What variables do I have?" | one_exec | Namespace inspection -- needs `ns()` executed |
| 5 | "Show me how to define a Node, then create one for me" | mixed | Both illustrative (showing definition) and executable (creating the node) |

Each scenario prompt is identical across all three conventions. Only the system prompt differs.

## Open Questions

1. **Should `evals/` be a permanent directory or temporary?**
   - What we know: Evals run once to pick the winner. The code is infrastructure, not production.
   - What's unclear: Is there value in keeping evals around for regression testing if the system prompt changes?
   - Recommendation: Keep `evals/` in the repo but exclude from default test runs via the existing `e2e` marker. Useful if the prompt is ever revised.

2. **How many eval runs per scenario for statistical confidence?**
   - What we know: LLM outputs are stochastic. A single run might succeed by luck.
   - What's unclear: How many repetitions are needed to establish "100% compliance."
   - Recommendation: Run each scenario 3 times (45 scenarios x 3 = 135 calls). If any run fails, the convention fails for that model. This triples the cost but provides meaningful confidence. Total: ~24 minutes sequential, ~8 minutes with 3x parallelism.

3. **What happens to Candidate C (inverse) silent-failure validation?**
   - What we know: Inverse convention is harder to validate because "forgetting" looks like "complying."
   - What's unclear: Can the eval reliably distinguish "AI used convention correctly" from "AI forgot convention and code happened to be illustrative"?
   - Recommendation: For the "no_exec" scenario, validate that the response contains at least one Python fence WITH the `:example` annotation (not just the absence of executable blocks). If the AI writes bare fences in an illustrative scenario, that's a compliance failure even if no code would execute.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `bae/repl/ai.py` (extract_code, AI._send, eval loop, _CODE_BLOCK_RE)
- Existing codebase: `bae/repl/ai_prompt.md` (current system prompt with fewshot)
- Existing codebase: `bae/repl/exec.py` (async_exec)
- Existing codebase: `tests/repl/test_ai.py` (TestExtractCode, TestEvalLoop)
- Existing codebase: `tests/conftest.py` (e2e marker)
- Anthropic models overview: https://platform.claude.com/docs/en/about-claude/models/overview -- model IDs confirmed
- Anthropic prompting best practices: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices -- instruction following, XML tags, fewshot design
- Anthropic multishot prompting: https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/multishot-prompting -- 3-5 examples, `<example>` tags, structured output compliance

### Secondary (MEDIUM confidence)
- Claude model tier behavior differences: Opus follows novel rules precisely; Haiku follows established patterns and may shortcut novel conventions. Based on Anthropic's own model descriptions and general experience.
- Regex negative lookahead for Candidate C: `(?!:example)` is standard Python regex. Verified by stdlib docs.

### Tertiary (LOW confidence)
- No specific prior art found for fence-annotation-based executable marking in LLM code generation. This appears to be a novel convention. Closest analogs are Jupyter cell types and GitHub Copilot's UI-based classification, but neither uses in-band marking.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- stdlib only, zero new deps, regex patterns verified
- Architecture: HIGH -- follows existing codebase patterns exactly (CLI subprocess, regex extraction, pytest harness)
- Pitfalls: HIGH -- identified from real codebase behavior (session contention, model tier differences, silent failure)
- Convention design: MEDIUM -- three candidates are well-specified but the winning convention is unknown until evals run. The research provides all the tools to evaluate but cannot predict the outcome.
- Eval harness: HIGH -- follows existing patterns (CLI subprocess, pytest e2e marker), standard parametrize

**Research date:** 2026-02-14
**Valid until:** 2026-03-14 (model IDs and CLI interface stable; convention eval results do not expire)
