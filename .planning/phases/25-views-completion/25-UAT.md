---
status: diagnosed
phase: 25-views-completion
source: [25-01-SUMMARY.md, 25-02-SUMMARY.md]
started: 2026-02-14T23:58:00Z
updated: 2026-02-15T00:12:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Ctrl+V cycles view modes
expected: Press Ctrl+V in the REPL. Toolbar should show "debug" badge. Press Ctrl+V again — toolbar shows "ai-self". Press Ctrl+V once more — toolbar indicator disappears (back to default user view).
result: pass

### 2. Debug view renders raw metadata
expected: In debug view (Ctrl+V once), trigger AI output. Instead of Rich panels, you should see raw lines like `[py] type=ai_exec label=1` as a header, followed by indented content lines.
result: pass

### 3. AI self-view renders semantic tags
expected: In AI self-view (Ctrl+V twice), trigger AI output. Content should show tags like `[ai-output]`, `[exec-code]`, `[exec-result]`, `[tool-call]`, `[tool-output]` as headers, with indented content below.
result: pass

### 4. User view shows Rich panels (unchanged)
expected: In default user view (Ctrl+V three times to cycle back), trigger AI code execution. Code should render in a Rich Panel with syntax highlighting, output in a separate panel below — same as Phase 24 behavior.
result: issue
reported: "Tool call translations (R: tags) dump entire file contents as [py] channel lines — very spammy. Should show something like 'read (some file)' instead of the full file contents."
severity: major

### 5. Toolbar hidden in default user view
expected: In default user view, the toolbar does NOT show any view mode badge — it's clean with no extra clutter.
result: pass

### 6. View switch updates all channels
expected: When switching views with Ctrl+V, ALL channel output adopts the new view format, not just the py channel.
result: pass

## Summary

total: 6
passed: 5
issues: 1
pending: 0
skipped: 0

## Gaps

- truth: "Tool call results display concisely in user view without dumping full file contents"
  status: failed
  reason: "User reported: Tool call translations (R: tags) dump entire file contents as [py] channel lines — very spammy. Should show something like 'read (some file)' instead of the full file contents."
  severity: major
  test: 4
  root_cause: "Eval loop (ai.py:124-133) writes full tool output to py channel. _exec_read() returns full file contents. UserView has no tool_result summarization — falls through to _render_prefixed() which prints every line."
  artifacts:
    - path: "bae/repl/ai.py"
      issue: "run_tool_calls output written to py channel unsummarized (lines 124-133, 286-294)"
    - path: "bae/repl/views.py"
      issue: "UserView has no special handling for tool_result metadata type"
  missing:
    - "Write summarized output to py channel for user display (e.g., 'read bae/repl/ai.py (513 lines)') while keeping full output for AI feedback"
  debug_session: ""
