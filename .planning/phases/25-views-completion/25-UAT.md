---
status: complete
phase: 25-views-completion
source: [25-01-SUMMARY.md, 25-02-SUMMARY.md, 25-03-SUMMARY.md]
started: 2026-02-15T01:20:00Z
updated: 2026-02-15T01:35:00Z
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
result: issue
reported: "bash did not get sent to tool-call:1, R:bae/node.py appears twice (in ai-output and as tool-call), and ls -la tool output repeated inline in AI response"
severity: minor

### 4. Tool call display is concise
expected: In default user view, ask the AI to read a file (triggering a tool call translation). The display should show a single concise gray italic line like "[py] read bae/repl/ai.py (513 lines)" — NOT the full file contents dumped line by line.
result: pass

### 5. AI still receives full tool output
expected: After a tool call in user view, the AI's next response should demonstrate it received and understood the full file contents (not just the summary). Ask it about specific content in the file it just read.
result: pass

### 6. Toolbar hidden in default user view
expected: In default user view, the toolbar does NOT show any view mode badge — it's clean with no extra clutter.
result: pass

### 7. Code execution still renders in Rich panels
expected: In default user view, trigger AI code execution. Code should render in a Rich Panel with syntax highlighting, output in a separate panel below — same as Phase 24 behavior.
result: issue
reported: "Raw [ai:1] lines show <run> block content before Rich panel renders, execution output appears above panel instead of grouped below, code duplicated as raw ai lines and inside Rich panel"
severity: minor

## Summary

total: 7
passed: 5
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "AI self-view provides structured feedback format with semantic tags for all tool call types"
  status: failed
  reason: "User reported: bash did not get sent to tool-call:1, R:bae/node.py appears twice (in ai-output and as tool-call), and ls -la tool output repeated inline in AI response"
  severity: minor
  test: 3
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""

- truth: "AI code execution renders as polished framed panels with output grouped below"
  status: failed
  reason: "User reported: Raw [ai:1] lines show <run> block content before Rich panel renders, execution output appears above panel instead of grouped below, code duplicated as raw ai lines and inside Rich panel"
  severity: minor
  test: 7
  root_cause: ""
  artifacts: []
  missing: []
  debug_session: ""
