---
phase: 20-ai-eval-loop
verified: 2026-02-14T18:30:00Z
status: passed
score: 7/7
---

# Phase 20: AI Eval Loop Verification Report

**Phase Goal:** AI operates as a full agent — extracts and executes code/commands, sees results, retains cross-session context, and renders output properly

**Verified:** 2026-02-14T18:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                                   | Status     | Evidence                                                                         |
| --- | ------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------- |
| 1   | AI-generated Python code blocks are automatically extracted, executed, and results fed back            | ✓ VERIFIED | AI.__call__ eval loop, async_exec integration, 7 unit tests pass                 |
| 2   | AI sessions spawned from PY mode are attachable/selectable in NL mode                                  | ✓ VERIFIED | @N prefix routing, _switch_session, namespace["ai"] pointer, integration tests  |
| 3   | NL mode has a session selector when multiple AI sessions exist                                         | ✓ VERIFIED | @N prefix parsing in _dispatch, sticky session tracking                         |
| 4   | N concurrent AI prompts route namespace mutations to correct sessions                                  | ✓ VERIFIED | test_concurrent_sessions_namespace_mutations passes                              |
| 5   | On launch, AI context includes recent session history from the store                                   | ✓ VERIFIED | cross_session_context() called on first prompt, 5 unit tests                    |
| 6   | AI output renders markdown formatting in the terminal                                                  | ✓ VERIFIED | render_markdown via Rich, ANSI bridge, markdown flag, 6 tests                   |
| 7   | Ctrl-C task menu renders as numbered list in scrollback, not toolbar                                   | ✓ VERIFIED | _print_task_menu prints to scrollback, toolbar always renders normal            |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact                       | Expected                                                           | Status     | Details                                                   |
| ------------------------------ | ------------------------------------------------------------------ | ---------- | --------------------------------------------------------- |
| `bae/repl/channels.py`         | render_markdown() function and markdown-aware Channel._display    | ✓ VERIFIED | Lines 30-40 (render_markdown), 83-87 (markdown display)  |
| `bae/repl/shell.py`            | Task menu prints to scrollback, @N prefix routing, _ai_sessions   | ✓ VERIFIED | Lines 41-53 (_print_task_menu), 168 (dict), 314-320 (@N) |
| `bae/repl/ai.py`               | Eval loop, _send(), cross_session_context, label support          | ✓ VERIFIED | Lines 71-120 (eval loop), 122-177 (_send), 79-82 (cross) |
| `bae/repl/store.py`            | cross_session_context() method                                     | ✓ VERIFIED | Lines 145-158, filters debug and current session         |
| `tests/repl/test_channels.py`  | Markdown rendering tests                                           | ✓ VERIFIED | 6 new tests (lines 29-34 test names), all pass            |
| `tests/repl/test_ai.py`        | Eval loop + cross-session memory tests                             | ✓ VERIFIED | 16 new tests (7 eval loop, 9 multi-session), all pass     |
| `tests/repl/test_ai_integration.py` | Concurrent session routing tests                          | ✓ VERIFIED | 5 new tests (concurrent + @N prefix), all pass            |

### Key Link Verification

| From                       | To                         | Via                                         | Status     | Details                                                  |
| -------------------------- | -------------------------- | ------------------------------------------- | ---------- | -------------------------------------------------------- |
| bae/repl/channels.py       | rich.markdown.Markdown     | render_markdown function                    | ✓ WIRED    | Line 16 import, line 39 usage with Console force_terminal |
| bae/repl/channels.py       | prompt_toolkit ANSI        | print_formatted_text(ANSI(...))             | ✓ WIRED    | Line 13 import, line 87 usage                             |
| bae/repl/shell.py          | bae/repl/ai.py             | _get_or_create_session creates AI instances | ✓ WIRED    | Lines 218-225, keyed by label                             |
| bae/repl/ai.py             | bae/repl/store.py          | cross_session_context on first prompt       | ✓ WIRED    | Line 80 calls self._store.cross_session_context()        |
| bae/repl/shell.py          | namespace['ai']            | active session pointer updated on switch    | ✓ WIRED    | Lines 171, 231 set namespace["ai"] = self.ai              |
| bae/repl/ai.py             | bae/repl/exec.async_exec   | eval loop executes extracted code           | ✓ WIRED    | Line 19 import, line 101 call in eval loop                |
| bae/repl/ai.py             | AI.extract_code            | eval loop extracts code blocks              | ✓ WIRED    | Line 94 calls self.extract_code(response)                 |
| bae/repl/ai.py             | AI._send                   | eval loop feeds results back                | ✓ WIRED    | Line 89, 116 calls await self._send()                     |

### Requirements Coverage

Phase 20 maps to:
- AI-06: AI agent eval loop (SATISFIED)
- STORE-03: Cross-session context retrieval (SATISFIED)
- REPL-10: Markdown rendering (SATISFIED)

| Requirement | Status      | Blocking Issue |
| ----------- | ----------- | -------------- |
| AI-06       | ✓ SATISFIED | None           |
| STORE-03    | ✓ SATISFIED | None           |
| REPL-10     | ✓ SATISFIED | None           |

### Anti-Patterns Found

None. Scanned all modified files:
- No TODO/FIXME/PLACEHOLDER comments
- No stub implementations (empty returns, console.log only)
- All error handling propagates CancelledError correctly
- All tests pass (85/85 for phase-specific tests, 233/233 full suite)

### Human Verification Required

**1. Visual markdown rendering**

**Test:** Start the REPL, enter NL mode, send a prompt like "show me markdown examples" and verify AI response renders with:
  - Headers (# ## ###) display as bold/larger text
  - **Bold** and *italic* render with ANSI formatting
  - Code blocks (```python) render with syntax highlighting or distinct styling
  - Lists (- bullet, 1. numbered) render with proper indentation

**Expected:** Rich markdown formatting visible in terminal output, not raw markdown syntax

**Why human:** Visual appearance requires human perception; automated tests verify ANSI codes exist but can't judge visual quality

**2. Task menu scrollback UX**

**Test:** 
  1. Start REPL, enter PY mode
  2. Submit 2-3 slow async tasks: `await asyncio.sleep(10)`, `await ai("test")`
  3. Press Ctrl-C while tasks running
  4. Verify numbered task list prints above the prompt (in scrollback)
  5. Verify toolbar shows normal widgets (mode, task count, cwd), not the task menu
  6. Press digit key to cancel a task
  7. Verify updated task list reprints to scrollback

**Expected:** Task menu is permanent scrollback content, not ephemeral toolbar content. Toolbar never hijacked.

**Why human:** Scrollback vs toolbar rendering distinction requires visual inspection

**3. Multi-session AI conversation flow**

**Test:**
  1. Start REPL in NL mode
  2. Send prompt "remember I like Python" (session 1, default)
  3. Send `@2 tell me about Rust` (creates session 2)
  4. Send "what do I like?" (should stay in session 2, no memory of Python)
  5. Send `@1 what do I like?` (switches back to session 1, should remember Python)
  6. In PY mode: `await ai("test")` (creates/uses default session)
  7. Switch to NL, send `@1 follow up` (should attach to same session)

**Expected:** Each session maintains independent conversation history. @N prefix switches sessions. PY mode sessions accessible via @N in NL mode.

**Why human:** Conversation coherence and memory requires human judgment of AI responses

**4. Cross-session context on fresh launch**

**Test:**
  1. Start REPL, have a short NL conversation with AI
  2. Exit REPL
  3. Start REPL again (new session)
  4. First AI prompt: "what did we just talk about?"
  5. Verify AI response references previous session content

**Expected:** AI includes `[Previous session context]` in first prompt, shows awareness of prior work

**Why human:** Requires multi-session workflow and human judgment of AI's contextual awareness

**5. Eval loop iteration and code execution**

**Test:**
  1. Start REPL in NL mode
  2. Send "create a variable called x with value 42, then print it"
  3. Verify AI response includes Python code block
  4. Verify code block auto-executes (no manual copy-paste)
  5. Verify execution output appears in [py] channel
  6. Verify AI sees the output and confirms success
  7. In PY mode, verify `x` exists: `x` should return 42

**Expected:** Code extraction → execution → feedback → AI response loop completes. Namespace mutations persist.

**Why human:** Full eval loop flow requires observing multi-step AI interaction and namespace state

---

_Verified: 2026-02-14T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
