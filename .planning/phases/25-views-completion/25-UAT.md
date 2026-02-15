---
status: testing
phase: 25-views-completion
source: [25-01-SUMMARY.md, 25-02-SUMMARY.md, 25-03-SUMMARY.md]
started: 2026-02-15T01:20:00Z
updated: 2026-02-15T01:20:00Z
---

## Current Test

number: 1
name: Ctrl+V cycles view modes
expected: |
  Press Ctrl+V in the REPL. Toolbar should show "debug" badge. Press Ctrl+V again — toolbar shows "ai-self". Press Ctrl+V once more — toolbar indicator disappears (back to default user view).
awaiting: user response

## Tests

### 1. Ctrl+V cycles view modes
expected: Press Ctrl+V in the REPL. Toolbar should show "debug" badge. Press Ctrl+V again — toolbar shows "ai-self". Press Ctrl+V once more — toolbar indicator disappears (back to default user view).
result: [pending]

### 2. Debug view renders raw metadata
expected: In debug view (Ctrl+V once), trigger AI output. Instead of Rich panels, you should see raw lines like `[py] type=ai_exec label=1` as a header, followed by indented content lines.
result: [pending]

### 3. AI self-view renders semantic tags
expected: In AI self-view (Ctrl+V twice), trigger AI output. Content should show tags like `[ai-output]`, `[exec-code]`, `[exec-result]`, `[tool-call]`, `[tool-output]` as headers, with indented content below.
result: [pending]

### 4. Tool call display is concise
expected: In default user view, ask the AI to read a file (triggering a tool call translation). The display should show a single concise gray italic line like "[py] read bae/repl/ai.py (513 lines)" — NOT the full file contents dumped line by line.
result: [pending]

### 5. AI still receives full tool output
expected: After a tool call in user view, the AI's next response should demonstrate it received and understood the full file contents (not just the summary). Ask it about specific content in the file it just read.
result: [pending]

### 6. Toolbar hidden in default user view
expected: In default user view, the toolbar does NOT show any view mode badge — it's clean with no extra clutter.
result: [pending]

### 7. Code execution still renders in Rich panels
expected: In default user view, trigger AI code execution. Code should render in a Rich Panel with syntax highlighting, output in a separate panel below — same as Phase 24 behavior.
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0

## Gaps

[none yet]
