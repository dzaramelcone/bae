---
status: investigating
trigger: "Investigate why tool call translations (specifically `<R:filepath>` Read tags) dump entire file contents as `[py]` channel lines in the REPL, creating massive spam."
created: 2026-02-14T19:02:00Z
updated: 2026-02-14T19:10:00Z
---

## Current Focus

hypothesis: CONFIRMED - tool_result writes dump full output to py channel, views.py has no summarization for tool results
test: examined views.py to see if UserView summarizes tool_result metadata
expecting: find that tool_result falls through to _render_prefixed which dumps all lines
next_action: confirm root cause and formulate fix

## Symptoms

expected: Tool call results should display concisely, e.g., "read (some file)" instead of the full file contents
actual: <R:filepath> Read tags dump entire file contents as [py] channel lines in the REPL, creating massive spam
errors: none
reproduction: Use <R:filepath> tag in REPL, observe full file contents dumped to py channel
started: unknown - behavior exists now

## Eliminated

## Evidence

- timestamp: 2026-02-14T19:05:00Z
  checked: bae/repl/ai.py lines 286-294 (_exec_read function)
  found: _exec_read returns full file contents (truncated at 4000 chars via _MAX_TOOL_OUTPUT)
  implication: The function returns content, not a summary description

- timestamp: 2026-02-14T19:06:00Z
  checked: bae/repl/ai.py lines 124-133 (tool call eval loop)
  found: |
    tool_results = run_tool_calls(response)  # line 124
    for tag, output in tool_results:
        self._router.write("py", tag, mode="PY", metadata={"type": "tool_translated"})  # line 128-129
        if output:
            self._router.write("py", output, mode="PY", metadata={"type": "tool_result"})  # line 130-132
  implication: Tag is written to py channel (good), then full output is written to py channel (spam source)

- timestamp: 2026-02-14T19:08:00Z
  checked: bae/repl/views.py lines 52-69 (UserView.render)
  found: |
    UserView only special-cases "ai_exec" and "ai_exec_result" types.
    "tool_result" type falls through to _render_prefixed (line 69).
    _render_prefixed (lines 113-124) renders line-by-line with [py:label] prefix.
  implication: Every line of tool output gets printed with [py] prefix - no summarization

- timestamp: 2026-02-14T19:09:00Z
  checked: bae/repl/views.py lines 146-173 (AISelfView and DebugView)
  found: Both views also render line-by-line without summarization
  implication: The spam happens in all view modes, not just UserView

## Resolution

root_cause: |
  Tool call results are written directly to the py channel without summarization.

  Flow:
  1. run_tool_calls() (ai.py:379) executes <R:filepath> and returns (tag, full_file_contents)
  2. AI eval loop (ai.py:130-132) writes full output to py channel with type="tool_result"
  3. UserView.render() (views.py:52-69) only special-cases "ai_exec" and "ai_exec_result"
  4. "tool_result" falls through to _render_prefixed() which prints every line with [py] prefix

  Root cause: No view logic exists to summarize tool results. All three view modes
  (UserView, DebugView, AISelfView) render tool output line-by-line.

fix: |
  Three possible approaches:

  A. Add tool_result buffering to UserView (similar to ai_exec buffering):
     - Buffer tool_translated (the tag line like "<R:file>")
     - On tool_result, render grouped panel with tag + summarized output
     - Show first/last N lines or char count instead of full dump

  B. Change what gets written to py channel in ai.py:
     - Keep full output for feedback to AI (combined variable, line 135)
     - Write summarized output to py channel for user display
     - E.g., "read bae/repl/ai.py (513 lines, 20KB)"

  C. Hybrid: Add summary metadata to tool_result, let views choose:
     - Compute summary in run_tool_calls (line count, byte count, first lines)
     - Pass as metadata to router.write()
     - UserView can show summary, DebugView can show full for debugging

  Recommendation: Approach B is cleanest - fix at source (ai.py) rather than
  making every view handle summarization. The AI gets full output in feedback,
  user sees concise summary in display.

verification: |
  1. Use <R:filepath> on a large file in REPL
  2. Observe py channel shows summary like "read bae/repl/ai.py (513 lines)"
  3. Verify AI still gets full file contents in feedback (can answer questions about the file)
  4. Test with all view modes (user, debug, ai-self)
  5. Test with other tool types (Glob, Grep, Edit) to ensure consistent behavior

files_changed: []
