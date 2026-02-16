---
status: diagnosed
trigger: "Investigate why the GRAPH mode `list` command renders Rich table markup as raw ANSI escape codes instead of properly formatted output."
created: 2026-02-15T00:00:00Z
updated: 2026-02-15T00:10:00Z
---

## Current Focus

hypothesis: CONFIRMED - router.write() sends ANSI string, formatters receive it as plain content and render with FormattedText instead of ANSI()
test: Complete - traced full flow and confirmed pattern
expecting: Fix requires formatters to detect ANSI content and wrap with ANSI()
next_action: document root cause and fix approach

## Symptoms

expected: Rich table rendered as properly formatted table with box drawing characters
actual: Raw ANSI escape codes displayed with escape sequences visible (e.g., `?[1m`, `?[0m`)
errors: None - the output is displayed, just garbled
reproduction: Switch to GRAPH mode, run a graph, execute `list` command
started: Unknown - issue exists in current implementation

## Eliminated

(none yet)

## Evidence

- timestamp: 2026-02-15T00:01:00Z
  checked: graph_commands.py _cmd_list (line 117-140)
  found: _cmd_list creates Rich Table, calls _rich_to_ansi(table) to convert to ANSI string, then shell.router.write("graph", ansi_string, mode="GRAPH")
  implication: The conversion to ANSI happens, but the string is sent as plain text through router

- timestamp: 2026-02-15T00:02:00Z
  checked: views.py _rich_to_ansi function (line 29-39)
  found: Creates Console with force_terminal=True, prints renderable to StringIO buffer, returns buf.getvalue()
  implication: This correctly generates ANSI escape sequences as a string

- timestamp: 2026-02-15T00:03:00Z
  checked: channels.py Channel.write and Channel._display (line 81-125)
  found: Channel._display() either delegates to formatter (if set) or renders with FormattedText. In the non-formatter path (lines 118-125), it treats content as plain text in a loop over splitlines()
  implication: When no formatter is set, ANSI codes in content are treated as literal text

- timestamp: 2026-02-15T00:04:00Z
  checked: shell.py _set_view (line 317-322)
  found: When view mode is set, all channels get a formatter assigned. UserView, DebugView, AISelfView all exist.
  implication: A formatter SHOULD be set on channels, so the non-formatter path might not be the issue

- timestamp: 2026-02-15T00:05:00Z
  checked: views.py ViewFormatter implementations
  found: UserView._render_prefixed (line 150-167) treats content as plain text, splits by lines, prints each with FormattedText. DebugView.render (line 177-186) also treats content as plain text. Neither use ANSI() wrapper.
  implication: Even with formatters, the content is treated as plain text, not as ANSI-escaped strings

- timestamp: 2026-02-15T00:06:00Z
  checked: How _rich_to_ansi is used elsewhere in views.py
  found: UserView._render_grouped_panel (line 128-129) does `ansi = _rich_to_ansi(panel)` then `print_formatted_text(ANSI(ansi))` - wraps in ANSI()
  implication: The ANSI() wrapper from prompt_toolkit is needed to interpret escape codes

- timestamp: 2026-02-15T00:07:00Z
  checked: Pattern differences between working and broken Rich rendering
  found: UserView._render_grouped_panel prints directly with ANSI(). UserView._render_prefixed (used for non-special types) splits content as plain text and wraps in FormattedText. Graph commands send Rich-rendered content through router.write() which goes to _render_prefixed.
  implication: The mismatch is architectural - Rich content goes through a plain-text rendering path

- timestamp: 2026-02-15T00:08:00Z
  checked: What metadata graph_commands currently pass
  found: _cmd_list line 140: router.write("graph", ansi_string, mode="GRAPH") - no metadata. _cmd_inspect line 206: router.write("graph", ansi_string, mode="GRAPH") - no metadata. Other commands pass plain strings.
  implication: No signal to formatters that content contains ANSI codes

## Resolution

root_cause: _cmd_list and _cmd_inspect call router.write() with ANSI-escaped strings (from _rich_to_ansi()), but the channel formatters (UserView, DebugView, AISelfView) receive this content and render it with FormattedText, treating the ANSI escape codes as literal characters.

The pattern in UserView._render_grouped_panel shows the correct approach:
- Line 128-129: `ansi = _rich_to_ansi(panel)` then `print_formatted_text(ANSI(ansi))`
- The ANSI() wrapper from prompt_toolkit is REQUIRED to interpret escape sequences

The formatters currently use _render_prefixed (UserView line 150-167) and similar plain-text rendering for all non-special content types. They split by lines and wrap each in FormattedText with channel prefix, which escapes/displays the raw escape codes.

fix: Add metadata to indicate ANSI-formatted content, then have formatters check for this metadata and wrap content with ANSI() instead of treating as plain text.

Proposed approach:
1. In graph_commands.py: Add metadata={"type": "ansi"} to router.write() calls that pass _rich_to_ansi() output
2. In views.py formatters: Check if metadata.get("type") == "ansi", if so call print_formatted_text(ANSI(content)) directly
3. This preserves channel visibility, store recording, and formatter architecture while enabling Rich rendering

Alternative (simpler but breaks architecture):
- Have _cmd_list and _cmd_inspect print directly via print_formatted_text(ANSI(...))
- Bypasses router entirely, breaks channel visibility toggles and store recording
- NOT RECOMMENDED

verification: (pending - no fix applied per instructions)
files_changed: []
