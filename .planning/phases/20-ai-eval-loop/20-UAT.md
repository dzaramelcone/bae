---
status: diagnosed
phase: 20-ai-eval-loop
source: [20-01-SUMMARY.md, 20-02-SUMMARY.md, 20-03-SUMMARY.md]
started: 2026-02-14T13:00:00Z
updated: 2026-02-14T13:40:00Z
---

## Current Test

[testing complete]

## Tests

### 1. AI markdown rendering
expected: In NL mode, send a prompt that produces markdown. Response renders with formatted headers, bold, code, and lists — not raw markdown text. Output on [ai] channel with ANSI formatting.
result: issue
reported: "bit messy - its starting to hallucinate my responses also. AI writes print() code blocks instead of answering naturally, eval loop fires on them, then AI fabricates what the execution output looks like (e.g. claims 500+ sessions when it can't know that)"
severity: major

### 2. Task menu in scrollback
expected: Start a long-running task (e.g., `await asyncio.sleep(30)` in PY mode). Press Ctrl-C. A numbered task list prints ABOVE the prompt as permanent scrollback. The toolbar continues showing normal widgets (mode, task count).
result: issue
reported: "Ctrl-C task menu works correctly (numbered list in scrollback, digit cancel works). But creating unawaited coroutines in PY mode (e.g. [asyncio.sleep(30) for _ in range(20)] without await) crashes the entire REPL with RuntimeWarning: coroutine 'sleep' was never awaited"
severity: blocker

### 3. Multi-session AI via @N prefix
expected: In NL mode, type `@2 hello` — a second AI session is created. Type a follow-up without prefix — it stays on session 2 (sticky). Type `@1 back to first` — switches to session 1. `ns()` or checking `ai` in namespace shows the active session label.
result: issue
reported: "looks like the formatter doesnt show the session number. [ai] channel label has no session indicator (e.g. [ai:1] vs [ai:2]). ns() shows ai:1 in repr but channel output doesn't distinguish sessions. Also AI goes on runaway eval loop generating code blocks repeatedly."
severity: major

### 4. Cross-session memory
expected: Exit cortex and re-launch. Send an AI prompt. The AI response should show awareness of what was discussed/done in the previous session (cross-session context injected on first prompt).
result: issue
reported: "seems to be working (AI picks up previous session context about Graph exploration) but not seeing the REPL output. [py] lines show code being executed but actual results (print output, return values, ns() output) are missing from display."
severity: major

### 5. AI eval loop — auto code execution
expected: In NL mode, ask the AI something that requires computation (e.g., "what's 2**100?"). The AI should write a Python code block, which gets automatically extracted and executed in the REPL namespace. The execution result feeds back to the AI, which then presents the answer incorporating the result.
result: issue
reported: "eval loop mechanics work — code extracted, executed, correct result fed back to AI which gives correct answer. But execution output not visible to user, only piped silently to AI. Need to tee output to [py] channel display as well."
severity: minor

### 6. Concurrent AI sessions from PY mode
expected: In PY mode, run two AI calls concurrently: `await asyncio.gather(ai("what is 1+1?"), ai("what is 2+2?"))`. Both complete without errors. Responses interleave on the [ai] channel. Namespace mutations from both are preserved.
result: issue
reported: "Concurrent execution works — both gather calls complete, responses interleave on [ai]. But runaway eval loop: both sessions keep generating code blocks repeatedly instead of answering concisely. Hits iteration limit. Same prompt engineering issue as tests 1/3."
severity: major

## Summary

total: 6
passed: 0
issues: 6
pending: 0
skipped: 0

## Gaps

- truth: "AI answers naturally in NL and only writes code when computation/inspection is needed"
  status: failed
  reason: "User reported: AI writes print() code blocks instead of answering naturally, eval loop fires on every response, AI fabricates execution output"
  severity: major
  test: 1
  root_cause: "ai_prompt.md rule 'Use python fences for tool calls. 1 fence per turn' forces AI to write code for every response. All examples show code blocks, no NL response examples. Combined with eval loop, creates respond->extract->execute->respond spiral."
  artifacts:
    - path: "bae/repl/ai_prompt.md"
      issue: "Rules section forces code blocks on every turn; no guidance on when to answer naturally"
  missing:
    - "Rewrite Rules to say code is ONLY for inspection/computation, not general Q&A"
    - "Add 'When to write code' section with natural language examples"
    - "Add NL-only response examples"
  debug_session: ""

- truth: "PY mode handles unawaited coroutines gracefully without crashing the REPL"
  status: failed
  reason: "User reported: [asyncio.sleep(30) for _ in range(20)] without await crashes entire REPL"
  severity: blocker
  test: 2
  root_cause: "shell.py _dispatch PY handler only checks asyncio.iscoroutine(result) for single coroutines. A list of coroutines passes this check, gets repr'd, and the unawaited coroutines crash the event loop during garbage collection."
  artifacts:
    - path: "bae/repl/shell.py"
      issue: "_dispatch PY mode (line 293) only checks iscoroutine, not collections containing coroutines"
    - path: "bae/repl/exec.py"
      issue: "async_exec only handles single coroutine results, not collections"
  missing:
    - "Add _contains_coroutines() helper to detect coroutines in collections"
    - "Close unawaited coroutines and show warning instead of repr'ing them"
  debug_session: ".planning/debug/unawaited-coroutines-crash.md"

- truth: "[ai] channel output includes session indicator (e.g. [ai:1]) to distinguish multi-session responses"
  status: failed
  reason: "User reported: formatter doesnt show the session number. All output shows [ai] with no session label."
  severity: major
  test: 3
  root_cause: "Channel._display() uses self.label which is f'[{self.name}]' = '[ai]'. Session label is passed in metadata but _display() ignores metadata. Need to format label as [ai:N] when metadata contains label."
  artifacts:
    - path: "bae/repl/channels.py"
      issue: "Channel._display() doesn't use metadata to enhance label with session indicator"
  missing:
    - "Pass metadata to _display(), format label as [ai:N] when label present in metadata"
  debug_session: ""

- truth: "Eval loop executed code output is visible to the user in the terminal"
  status: failed
  reason: "User reported: [py] lines show code being executed but actual results missing from display"
  severity: major
  test: 4
  root_cause: "ai.py eval loop writes code to [py] channel (line 112) but execution results (stdout + return values) are only collected in results list for AI feedback. Never written to any channel for user display."
  artifacts:
    - path: "bae/repl/ai.py"
      issue: "Eval loop line 112 writes code but not execution output. Results silently piped to AI only."
  missing:
    - "Add router.write() for execution results after the code write (tee to user AND AI)"
  debug_session: ""

- truth: "Eval loop execution output is teed to user display, not just piped silently to AI"
  status: failed
  reason: "User reported: eval loop works but output not visible to user"
  severity: minor
  test: 5
  root_cause: "Same as gap 4 — eval loop results only fed to AI, not displayed. Single router.write() addition."
  artifacts:
    - path: "bae/repl/ai.py"
      issue: "Missing router.write() for execution results"
  missing:
    - "Add router.write('py', output, ...) after each code execution in eval loop"
  debug_session: ""

- truth: "AI responds concisely without runaway code generation loops"
  status: failed
  reason: "User reported: AI keeps generating code blocks repeatedly, hits max_eval_iters"
  severity: major
  test: 6
  root_cause: "Same as gap 1 — ai_prompt.md forces code on every turn. Concurrent sessions amplify the problem. Fix the prompt, and runaway loops disappear."
  artifacts:
    - path: "bae/repl/ai_prompt.md"
      issue: "Prompt forces code generation on every turn"
  missing:
    - "Same prompt rewrite as gap 1"
  debug_session: ""
