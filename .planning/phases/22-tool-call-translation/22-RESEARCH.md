# Phase 22: Tool Call Translation - Research

**Researched:** 2026-02-14
**Domain:** Regex-based AI response interception, tool-call-to-Python translation, eval loop extension
**Confidence:** HIGH

## Summary

Phase 22 adds a tool call translation layer to the eval loop in `AI.__call__()`. The AI is taught a set of terse shorthand tags (`<R:filepath>`, `<W:filepath>`, `<E:filepath:line_start-line_end>`, `<G:pattern>`, `<Grep:pattern>`) in its system prompt. When the eval loop encounters these tags in a response (outside of `<run>` blocks), it translates them to Python code, executes that code in the shared namespace, and feeds results back to the AI. The user sees a visible indicator that a tool call was translated and executed.

This is a fundamentally different approach from the original v5.0 vision (FEATURES.md), which proposed detect-reject-retry for hallucinated tool calls. Instead, the requirements specify **translation**: the AI intentionally uses terse tags as a shorthand vocabulary, and the system transparently converts them to Python. The AI does not need to know Python filesystem APIs -- it uses the shorthand, and the system handles the rest.

The implementation sits entirely within `bae/repl/ai.py` (detection + translation + integration with eval loop) and `bae/repl/ai_prompt.md` (teaching the AI the shorthand syntax). All translations use Python stdlib (`pathlib`, `glob`, `re`, `subprocess`). No new dependencies. The Phase 21 `<run>` convention is preserved -- tool call tags are a separate detection pass that runs BEFORE `extract_executable()`, and translated code flows through the same `async_exec` path.

**Primary recommendation:** Build a `translate_tool_calls()` pure function that takes response text and returns either translated Python code or None. Insert it into the eval loop between `_send()` and `extract_executable()`. Teach the shorthand in the system prompt with fewshot examples. Write to a new channel or use metadata to indicate translated execution.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| re (stdlib) | N/A | Regex detection of tool call tags in AI responses | Already used for `_EXEC_BLOCK_RE`. Known patterns, not arbitrary XML parsing. |
| pathlib (stdlib) | N/A | File read/write/edit translations | Already in REPL namespace (`os` imported). Standard file API. |
| glob (stdlib) | N/A | Glob pattern translations | stdlib glob.glob() for `<G:pattern>` |
| subprocess (stdlib) | N/A | Grep translation via `grep` subprocess | `asyncio.create_subprocess_exec` already used throughout codebase |
| ast (stdlib) | N/A | No new usage -- already imported in exec.py | |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | | | Zero new dependencies per prior decision |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom grep in Python (re module) | subprocess grep | subprocess grep is faster on large files, matches `rg`/`grep` behavior users expect. But adds subprocess overhead. For simplicity, use Python `re` on file content. |
| XML parser for tool call detection | Regex | Out of scope per REQUIREMENTS.md. Regex on known terse patterns is correct and simple. |
| Separate translator module | Functions in ai.py | Single module keeps translation logic next to the eval loop that calls it. Extract later if it grows. |

## Architecture Patterns

### Recommended File Structure
```
bae/repl/
    ai.py              # MODIFIED -- add tool call detection + translation in eval loop
    ai_prompt.md        # MODIFIED -- add terse tool call shorthand fewshot
tests/repl/
    test_ai.py          # MODIFIED -- add TestToolCallTranslation tests
```

### Pattern 1: Tool Call Tag Syntax

The terse tag format from the requirements:

| Tag | Syntax | Purpose | Example |
|-----|--------|---------|---------|
| Read | `<R:filepath>` | Read file contents | `<R:src/main.py>` |
| Write | `<W:filepath>` | Write content to file | `<W:output.txt>` followed by content |
| Edit | `<E:filepath:line_start-line_end>` | Read/edit a file region | `<E:src/main.py:10-25>` |
| Glob | `<G:pattern>` | Glob search | `<G:src/**/*.py>` |
| Grep | `<Grep:pattern>` | Content search | `<Grep:def main>` |

**Tag detection regex:**

```python
# Detect terse tool call tags OUTSIDE of <run> blocks and code fences
_TOOL_CALL_RE = re.compile(
    r"<(R|W|E|G|Grep):([^>]+)>",
)
```

The regex captures two groups: (1) the tool type letter, (2) the argument string. For Edit, the argument contains `filepath:line_start-line_end` which needs secondary parsing.

**Fence exclusion:** Per prior decision, "tool call regex must exclude code fences to avoid false positives on legitimate XML in Python." Before scanning for tool call tags, strip `<run>...</run>` blocks and markdown fences from the text. Scan only the prose portions.

### Pattern 2: Translation Functions

Each tool type maps to a pure translation function that takes the captured argument and returns Python code as a string:

```python
def _translate_read(filepath: str) -> str:
    """Translate <R:filepath> to Python file read."""
    return f"print(open({filepath!r}).read())"

def _translate_write(filepath: str, content: str) -> str:
    """Translate <W:filepath> to Python file write."""
    return f"open({filepath!r}, 'w').write({content!r})"

def _translate_edit(filepath: str, start: int, end: int) -> str:
    """Translate <E:filepath:start-end> to Python line-range read."""
    return (
        f"lines = open({filepath!r}).readlines()\n"
        f"print(''.join(lines[{start-1}:{end}]))"
    )

def _translate_glob(pattern: str) -> str:
    """Translate <G:pattern> to Python glob search."""
    return f"import glob; print('\\n'.join(sorted(glob.glob({pattern!r}, recursive=True))))"

def _translate_grep(pattern: str) -> str:
    """Translate <Grep:pattern> to Python content search."""
    return (
        f"import subprocess; "
        f"r = subprocess.run(['grep', '-rn', {pattern!r}, '.'], "
        f"capture_output=True, text=True); "
        f"print(r.stdout[:2000] if r.stdout else '(no matches)')"
    )
```

**Output truncation:** Read, Glob, and Grep translations truncate output to prevent context explosion. The AI already handles `MAX_CONTEXT_CHARS = 2000` for namespace context. Tool call output should respect a similar budget. Truncation happens in the Python code itself (e.g., `print(content[:4000])`) so the AI sees the truncation in its feedback.

### Pattern 3: Write Tag Content Extraction

`<W:filepath>` requires content from the response. The content follows the tag, typically in one of these formats:

```
<W:output.txt>
file content here
multiple lines
</W>
```

The Write tag needs a closing `</W>` to delimit the content body. The regex for Write extraction:

```python
_WRITE_RE = re.compile(
    r"<W:([^>]+)>\s*\n(.*?)\n\s*</W>",
    re.DOTALL,
)
```

### Pattern 4: Edit Tag with Content

`<E:filepath:start-end>` in READ mode just reads lines. But for actual EDITING, the AI needs to provide replacement content:

```
<E:src/main.py:10-15>
replacement content
for those lines
</E>
```

When `</E>` follows with content, it is an edit (replace lines). When the tag appears alone, it is a read (show lines). Detection:

```python
_EDIT_RE = re.compile(
    r"<E:([^:>]+):(\d+)-(\d+)>\s*\n(.*?)\n\s*</E>",
    re.DOTALL,
)
# If no closing tag with content, it's a line-range read:
_EDIT_READ_RE = re.compile(
    r"<E:([^:>]+):(\d+)-(\d+)>",
)
```

### Pattern 5: Eval Loop Integration

The translation step inserts between `_send()` and `extract_executable()`:

```python
async def __call__(self, prompt: str) -> str:
    # ... context building, _send ...
    response = await self._send(full_prompt)
    self._router.write("ai", response, mode="NL", ...)

    for _ in range(self._max_eval_iters):
        # NEW: Check for tool call tags first
        tool_code = self.translate_tool_calls(response)
        if tool_code is not None:
            # Execute translated code
            output = await self._exec_and_capture(tool_code)
            # Visual indicator for user
            self._router.write("py", tool_code, mode="PY",
                metadata={"type": "tool_translated", "label": self._label})
            self._router.write("py", output, mode="PY",
                metadata={"type": "tool_result", "label": self._label})
            # Feed result back
            response = await self._send(f"[Tool output]\n{output}")
            self._router.write("ai", response, mode="NL", ...)
            continue

        # Existing: check for <run> blocks
        code, extra = self.extract_executable(response)
        if code is None:
            break
        # ... existing exec logic ...
```

**Key design decisions:**
- Tool call translation runs BEFORE `extract_executable()` -- if the AI uses tool call tags, it takes precedence over `<run>` blocks in the same response
- Translation uses a SEPARATE metadata type (`tool_translated`, `tool_result`) so views can distinguish translated tool calls from explicit AI code
- The feedback prompt says `[Tool output]` (not `[Output]`) so the AI knows its tool call was serviced
- Translation counts against `max_eval_iters` like normal code execution

### Pattern 6: System Prompt Additions

The AI needs to learn the terse syntax. Add to `ai_prompt.md`:

```markdown
## File and search tools
You have shorthand tags for file operations. These execute directly -- no need for <run> blocks.

| Tag | Purpose | Example |
|-----|---------|---------|
| `<R:path>` | Read file | `<R:src/main.py>` |
| `<W:path>content</W>` | Write file | `<W:out.txt>hello</W>` |
| `<E:path:start-end>` | Show lines | `<E:src/main.py:10-25>` |
| `<E:path:start-end>new content</E>` | Replace lines | `<E:src/main.py:10-15>fixed code</E>` |
| `<G:pattern>` | Find files | `<G:src/**/*.py>` |
| `<Grep:pattern>` | Search content | `<Grep:def main>` |

Use these instead of writing Python file I/O code.
```

With 2-3 fewshot examples showing usage:

```markdown
<example>
User: what's in src/main.py?
Assistant: <R:src/main.py>
</example>

<example>
User: find all Python test files
Assistant: <G:tests/**/*.py>
</example>

<example>
User: search for uses of asyncio.gather
Assistant: <Grep:asyncio.gather>
</example>
```

### Pattern 7: Visible Indicator (AIHR-08)

When a tool call is translated and executed, the user needs a visible indicator. Options:

**Recommendation: Use existing channel with distinct metadata type.**

The `[py]` channel already shows AI-executed code. Tool call translations write with `metadata={"type": "tool_translated"}` for the code and `metadata={"type": "tool_result"}` for output. The channel display can use the label to differentiate:

```
[py:1] # translated: <R:src/main.py> -> open('src/main.py').read()
[py:1] (file contents...)
```

Alternatively, a future Phase 23/24 view formatter can render translated tool calls with a distinctive badge or icon. For Phase 22, the metadata annotation is sufficient -- the existing `[py]` channel renders the translated code and output, and the metadata `type` field distinguishes it from manual code execution.

### Anti-Patterns to Avoid

- **Full XML parsing:** The tags are simple, fixed-format shorthands. Do not build an XML parser. Regex is correct.
- **Multiple tool calls per response:** Like `<run>` blocks, process only the FIRST tool call tag per response. If the AI emits multiple tags, execute the first and ignore the rest. Feedback tells the AI what was executed.
- **Unbounded output:** File reads, grep results, and glob results can be enormous. Always truncate output in the translation. A 10MB file read crashing the context window is a real risk.
- **Writing to arbitrary paths:** The Write translation should NOT silently write to arbitrary filesystem locations. Consider limiting to CWD or requiring confirmation for paths outside the project. For Phase 22, write to the path as given (the AI operates in user context, like any REPL code) but log the write to the debug channel.
- **Translating tags inside code:** If the AI writes `<R:foo.py>` inside a `<run>` block or a markdown fence, it is illustrative/literal, not a tool call. Strip fenced regions before scanning for tags.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File reading | Custom file reader class | `open(path).read()` via translation | One line of Python. No abstraction needed. |
| File writing | Custom file writer with validation | `open(path, 'w').write(content)` via translation | Same as what the user would type in PY mode. |
| Glob search | Custom recursive file walker | `glob.glob(pattern, recursive=True)` | stdlib handles all glob patterns correctly. |
| Content search | Custom grep implementation | `subprocess.run(['grep', '-rn', ...])` or Python `re` on file content | grep is battle-tested. For pure-Python, iterate lines with `re.search`. |
| Tool call routing | Plugin system or registry | Simple if/elif chain on the captured tool type letter | 5 tool types. No extensibility needed. YAGNI. |

**Key insight:** Every translation is a one-liner Python expression. The complexity is in detection (regex) and integration (eval loop wiring), not in the translations themselves.

## Common Pitfalls

### Pitfall 1: False Positives on Legitimate Angle Brackets

**What goes wrong:** The `<R:...>` regex matches text like `<Result: 42>` or `<Response: ok>` in AI prose or Python repr output.
**Why it happens:** The tag format uses `<LETTER:content>` which could match other colon-prefixed angle bracket patterns.
**How to avoid:** The regex should be strict: only match exact single-letter tool tags R, W, E, G or the word Grep. Use `^` or lookbehind to ensure the tag starts at a word boundary or line start. Better: require the tag to appear on its own line (not embedded in prose). The fewshot examples should show tags on separate lines.
**Warning signs:** AI writes "The result is <R: 3.14>" and the system tries to read a file named " 3.14".

### Pitfall 2: Tool Tags Inside Code Fences Cause Double Execution

**What goes wrong:** AI writes a `<run>` block containing `<R:foo.py>` as a literal string or in a comment. The translation layer detects the tag and ALSO the eval loop extracts the `<run>` block.
**Why it happens:** Translation scans the full response text without excluding fenced regions.
**How to avoid:** Strip `<run>...</run>` blocks AND markdown fences from the text BEFORE scanning for tool call tags. Only scan the "prose" portion of the response. This is the same exclusion the prior decision mandates: "Tool call regex must exclude code fences to avoid false positives on legitimate XML in Python."
**Warning signs:** The same code executes twice -- once as a tool translation and once as a `<run>` block.

### Pitfall 3: Unbounded File Read Crashes Context Window

**What goes wrong:** AI writes `<R:/dev/urandom>` or `<R:huge_dataset.csv>` and the translation reads the entire file into the response, exhausting the context window or hanging the process.
**Why it happens:** No size limit on file reads. The translation naively does `open(path).read()`.
**How to avoid:** Truncate all tool call output to a maximum (e.g., 4000 characters). The truncation should be in the generated Python code: `content = open(path).read()[:4000]`. The AI sees `(truncated)` in the feedback and can request specific line ranges via `<E:path:start-end>` for targeted reading.
**Warning signs:** AI response takes minutes to arrive because the feedback prompt is 100KB.

### Pitfall 4: Write Tag Delimiter Ambiguity

**What goes wrong:** The AI writes `<W:foo.txt>` but doesn't include `</W>` closing tag. Or the content contains `</W>` as literal text. The regex either captures nothing or captures wrong content.
**Why it happens:** The AI may not consistently follow the closing tag convention, especially if the fewshot examples are unclear.
**How to avoid:** Require explicit `</W>` closing tag for Write. If missing, do not execute the write -- feed back "Write requires closing `</W>` tag." Keep fewshot examples consistent. Consider: if no `</W>` is found, treat everything from the tag to the end of the response as the content (greedy fallback), but this is dangerous. Strict closing tag is safer.
**Warning signs:** Files written with garbage content or partial writes.

### Pitfall 5: Edit Line Numbers Off-By-One

**What goes wrong:** AI says `<E:file.py:10-15>` but means lines 10-15 inclusive. The translation uses Python slicing `lines[9:15]` (0-indexed, exclusive end) but the AI counts from 1 (inclusive both ends).
**Why it happens:** Python list slicing is 0-based with exclusive end. Humans and AI count lines starting at 1 with inclusive ranges.
**How to avoid:** Document the convention explicitly: "Line numbers are 1-based, inclusive." Translation: `lines[start-1:end]` (0-based start, exclusive end = inclusive end in 1-based). Test with concrete examples.
**Warning signs:** AI edits the wrong lines, or reads one line fewer than expected.

### Pitfall 6: Grep Subprocess Hangs on Binary Files

**What goes wrong:** `grep -rn pattern .` recurses into `.venv/`, `.git/`, or binary files. It takes forever or produces garbage output.
**Why it happens:** Default recursive grep searches everything.
**How to avoid:** Use `grep --include='*.py' -rn pattern .` or better, use Python-native search: iterate files with glob, read each, search with `re.search`. For Phase 22, exclude `.venv`, `.git`, `node_modules`, `__pycache__` from grep. Add `--binary-files=without-match` flag.
**Warning signs:** Grep results contain binary garbage or take > 10 seconds.

### Pitfall 7: AI Confuses Tool Tags with Regular Response Text

**What goes wrong:** AI attempts to explain the tool call syntax to the user by writing `<R:filepath>` in prose, and the system intercepts it as an actual tool call.
**Why it happens:** The AI mentioning its own syntax in explanatory text looks identical to an actual tool call invocation.
**How to avoid:** The fewshot examples should show tool calls on their own line, never embedded in prose. The regex can require the tag to be the ONLY content on its line (after optional whitespace). This distinguishes `Let me read the file: <R:foo.py>` (embedded -- do not translate) from a standalone tag on its own line.
**Warning signs:** AI explains "you can use `<R:path>` to read files" and the system tries to read a file named "path".

## Code Examples

### Tool Call Detection (entry point)

```python
# In ai.py -- new constant
_TOOL_TAG_RE = re.compile(
    r"^[ \t]*<(R|W|E|G|Grep):([^>]+)>",
    re.MULTILINE,
)

# Write requires content extraction
_WRITE_TAG_RE = re.compile(
    r"<W:([^>]+)>\s*\n(.*?)\n\s*</W>",
    re.DOTALL,
)

# Edit with replacement content
_EDIT_REPLACE_RE = re.compile(
    r"<E:([^:>]+):(\d+)-(\d+)>\s*\n(.*?)\n\s*</E>",
    re.DOTALL,
)
```

### Translation Router

```python
_MAX_TOOL_OUTPUT = 4000  # chars

def translate_tool_calls(text: str) -> str | None:
    """Detect first terse tool call tag in prose and return Python code.

    Returns None if no tool call tags found. Skips tags inside
    <run>...</run> blocks or markdown fences.
    """
    # Strip executable and illustrative blocks before scanning
    prose = _EXEC_BLOCK_RE.sub("", text)
    prose = re.sub(r"```.*?```", "", prose, flags=re.DOTALL)

    # Check Write (needs content body)
    wm = _WRITE_TAG_RE.search(prose)
    if wm:
        return _translate_write(wm.group(1), wm.group(2))

    # Check Edit-with-replacement
    em = _EDIT_REPLACE_RE.search(prose)
    if em:
        return _translate_edit_replace(
            em.group(1), int(em.group(2)), int(em.group(3)), em.group(4))

    # Check single-line tags
    m = _TOOL_TAG_RE.search(prose)
    if not m:
        return None

    tool, arg = m.group(1), m.group(2)
    if tool == "R":
        return _translate_read(arg)
    if tool == "E":
        return _translate_edit_read(arg)
    if tool == "G":
        return _translate_glob(arg)
    if tool == "Grep":
        return _translate_grep(arg)
    return None
```

### Individual Translators

```python
def _translate_read(filepath: str) -> str:
    fp = filepath.strip()
    return (
        f"_c = open({fp!r}).read()\n"
        f"print(_c[:{_MAX_TOOL_OUTPUT}])\n"
        f"if len(_c) > {_MAX_TOOL_OUTPUT}: print('... (truncated)')"
    )

def _translate_write(filepath: str, content: str) -> str:
    fp = filepath.strip()
    return (
        f"open({fp!r}, 'w').write({content!r})\n"
        f"print(f'Wrote {{len({content!r})}} chars to {fp}')"
    )

def _translate_edit_read(arg: str) -> str:
    # Parse filepath:start-end
    parts = arg.rsplit(":", 1)
    fp = parts[0].strip()
    if len(parts) == 2 and "-" in parts[1]:
        start, end = parts[1].split("-", 1)
        s, e = int(start), int(end)
        return (
            f"_lines = open({fp!r}).readlines()\n"
            f"for i, ln in enumerate(_lines[{s-1}:{e}], start={s}):\n"
            f"    print(f'{{i:4d}} | {{ln}}', end='')"
        )
    return _translate_read(fp)

def _translate_edit_replace(filepath: str, start: int, end: int, content: str) -> str:
    fp = filepath.strip()
    return (
        f"_lines = open({fp!r}).readlines()\n"
        f"_new = {content!r}.splitlines(True)\n"
        f"_lines[{start-1}:{end}] = _new\n"
        f"open({fp!r}, 'w').writelines(_lines)\n"
        f"print(f'Replaced lines {start}-{end} in {fp}')"
    )

def _translate_glob(pattern: str) -> str:
    p = pattern.strip()
    return (
        f"import glob as _g\n"
        f"_hits = sorted(_g.glob({p!r}, recursive=True))\n"
        f"print('\\n'.join(_hits[:{_MAX_TOOL_OUTPUT // 40}]))\n"
        f"if len(_hits) > {_MAX_TOOL_OUTPUT // 40}: "
        f"print(f'... ({{len(_hits)}} total)')"
    )

def _translate_grep(pattern: str) -> str:
    p = pattern.strip()
    return (
        f"import subprocess as _sp\n"
        f"_r = _sp.run("
        f"['grep', '-rn', '--include=*.py', "
        f"'--exclude-dir=.venv', '--exclude-dir=.git', "
        f"'--exclude-dir=__pycache__', "
        f"{p!r}, '.'], "
        f"capture_output=True, text=True, timeout=10)\n"
        f"_out = _r.stdout[:{_MAX_TOOL_OUTPUT}]\n"
        f"print(_out if _out else '(no matches)')\n"
        f"if len(_r.stdout) > {_MAX_TOOL_OUTPUT}: print('... (truncated)')"
    )
```

### Eval Loop Integration

```python
# In AI.__call__, inside the for loop, BEFORE extract_executable:

    tool_code = translate_tool_calls(response)
    if tool_code is not None:
        output = ""
        try:
            result, captured = await async_exec(tool_code, self._namespace)
            if asyncio.iscoroutine(result):
                result = await result
            output = captured
            if result is not None:
                output += repr(result)
            output = output or "(no output)"
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            output = traceback.format_exc()

        self._router.write("py", tool_code, mode="PY",
            metadata={"type": "tool_translated", "label": self._label})
        if output:
            self._router.write("py", output, mode="PY",
                metadata={"type": "tool_result", "label": self._label})

        feedback = f"[Tool output]\n{output}"
        response = await self._send(feedback)
        self._router.write("ai", response, mode="NL",
            metadata={"type": "response", "label": self._label})
        continue
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| AI hallucinates `<tool_use>` XML with fabricated results (v4.0 UAT-2 defect) | Teach AI terse shorthand tags, translate to Python, execute transparently | Phase 22 | AI can do file I/O and search without knowing Python stdlib APIs |
| Original v5.0 plan: detect-reject-retry (FEATURES.md "anti-feature") | Translation: detect-translate-execute | Roadmap evolution | AI tool calls become useful instead of error conditions |
| No file system access from AI (Python-only in namespace) | AI can read/write/edit/glob/grep via shorthand tags | Phase 22 | Major capability expansion within existing security model |

**Design evolution:** The original FEATURES.md (pre-Phase 21) explicitly listed "Semantic parsing of tool-use XML" as an anti-feature, recommending "simple regex detect + reject + retry." The REQUIREMENTS.md and ROADMAP.md evolved this into a translation approach -- the AI uses intentional shorthand tags (not hallucinated XML), and the system translates them to Python. This is a deliberate pivot from rejection to enablement.

**AIHR-01 status:** Deferred. The system prompt does NOT currently have a "no tools" constraint. Phase 22 takes the opposite approach: instead of telling the AI it has no tools, it gives the AI a DIFFERENT tool vocabulary (terse tags) that the system translates.

## Open Questions

1. **Should tool translations use `async_exec` or a separate execution path?**
   - What we know: `async_exec` handles top-level await, captures stdout, and manages the namespace. Tool call translations are simple synchronous Python.
   - What's unclear: Whether tool translations need the full `async_exec` machinery or could use a simpler `exec()`.
   - Recommendation: Use `async_exec` for consistency. It handles stdout capture, and grep translation uses subprocess which could benefit from async. Simpler to reuse the existing path than maintain a second one.

2. **Should multiple tool calls per response be supported?**
   - What we know: `<run>` blocks follow a "first only" policy (Phase 21). Tool calls could follow the same pattern.
   - What's unclear: Whether the AI will naturally emit multiple tool tags in one response (e.g., read a file AND grep for something).
   - Recommendation: Execute only the FIRST tool call tag per response, matching the `<run>` block policy. The AI can chain operations across eval loop iterations. This avoids ordering ambiguity and keeps the feedback loop simple.

3. **How should Write handle file creation vs overwrite?**
   - What we know: `open(path, 'w')` creates or overwrites. The AI is operating in the user's cwd.
   - What's unclear: Whether the user expects confirmation before overwrites.
   - Recommendation: Write unconditionally for Phase 22 (matches what the user would do in PY mode). Log all writes to the debug channel. Confirmation dialogs are a future enhancement.

4. **Should grep use subprocess `grep` or pure Python?**
   - What we know: Subprocess grep is fast but adds external dependency. Python `re` on file contents is portable.
   - What's unclear: Performance characteristics on real codebases.
   - Recommendation: Use subprocess `grep` with `--include` and `--exclude-dir` flags. It is universally available on macOS/Linux (the target platforms), handles binary files correctly, and is significantly faster than Python line-by-line search on large codebases. The timeout (10s) prevents hangs.

5. **What is the relationship between tool calls and `<run>` blocks in the same response?**
   - What we know: The eval loop currently checks `extract_executable()` once per iteration. Tool call detection would be a new check.
   - What's unclear: What if the AI writes both `<R:foo.py>` AND a `<run>` block in the same response?
   - Recommendation: Tool call tags take precedence. Check for tool calls first. If found, execute the translation. If not found, fall through to `extract_executable()`. This means the AI can use EITHER mechanism but not both in the same response. The feedback from the tool call execution gives the AI the information it needs to decide whether to write a `<run>` block in the next response.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `bae/repl/ai.py` -- AI.__call__ eval loop (lines 72-140), extract_executable (lines 214-224), _EXEC_BLOCK_RE (lines 29-32)
- Existing codebase: `bae/repl/ai_prompt.md` -- current system prompt with `<run>` convention fewshot
- Existing codebase: `bae/repl/exec.py` -- async_exec() used for code execution
- Existing codebase: `bae/repl/channels.py` -- Channel._display with metadata support
- Existing codebase: `tests/repl/test_ai.py` -- TestExtractExecutable, TestEvalLoop patterns
- REQUIREMENTS.md: AIHR-02 through AIHR-08 requirements with exact tag syntax
- ROADMAP.md: Phase 22 success criteria with exact tag formats

### Secondary (MEDIUM confidence)
- v4.0 UAT-2 report (`20-UAT-2.md`): documented tool hallucination problem that Phase 22 addresses
- v4.0 milestone audit: confirmed "AI hallucinates tool calls" as deferred tech debt
- Research PITFALLS.md: Pitfall 4 (regex false positives), Pitfall 7 (feedback loop amplification) -- directly applicable
- Research FEATURES.md: original detect-reject-retry vision now evolved to translate-execute
- Research STACK.md: tool call regex patterns, CLI-level tool restrictions

### Tertiary (LOW confidence)
- The exact terse tag syntax (`<R:filepath>`, etc.) appears to originate from the roadmap/requirements, not from any external standard or AI convention research. Its effectiveness depends on whether Claude models follow this novel syntax reliably. The Phase 21 `<run>` tag convention achieved 100% compliance across models, which is a positive signal for XML-style tags in general.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- stdlib only, zero new deps, all patterns verified in codebase
- Architecture: HIGH -- follows existing eval loop patterns exactly (detection -> translation -> exec -> feedback)
- Pitfalls: HIGH -- identified from codebase evidence (false positives, output truncation, fence exclusion) and prior research (PITFALLS.md Pitfall 4, 7)
- Tag syntax compliance: MEDIUM -- novel syntax, but `<run>` tag 100% compliance in Phase 21 evals gives high confidence for XML-style tags

**Research date:** 2026-02-14
**Valid until:** 2026-03-14 (stable domain -- regex patterns, stdlib APIs, eval loop architecture)
