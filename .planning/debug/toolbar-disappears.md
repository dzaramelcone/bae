---
status: diagnosed
trigger: "Investigate why the bottom toolbar disappears while a task (AI or bash) is running in cortex."
created: 2026-02-13T00:00:00Z
updated: 2026-02-13T00:03:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: CONFIRMED - toolbar disappears because prompt_toolkit erases it when prompt_async() returns
test: Research architectural solutions to keep UI visible during task execution
expecting: Need to either keep prompt_toolkit active with background tasks, or use alternative UI approach
next_action: Document fix approaches in Resolution.fix

## Symptoms

expected: Toolbar should remain visible showing mode/cwd/task count during task execution
actual: Toolbar vanishes when running tasks (both bash commands like `sleep 5` and AI queries)
errors: None reported
reproduction: Launch cortex, observe toolbar at idle. Run `sleep 5` in BASH mode or AI query in NL mode. Toolbar disappears during execution.
started: Unknown - appears to be current behavior

## Eliminated

## Evidence

- timestamp: 2026-02-13T00:01:00Z
  checked: bae/repl/shell.py run() loop and _dispatch()
  found: run() loop at line 255-278: calls session.prompt_async() (line 260), then awaits _dispatch(text) (line 274). The toolbar is configured in __init__ with refresh_interval=1.0 (line 143) and bottom_toolbar=self._toolbar (line 142).
  implication: During prompt_async(), prompt_toolkit is active and renders toolbar. After prompt_async() returns, we await _dispatch() which can take seconds (AI task, sleep 5). During this await, prompt_async() is NOT active, so prompt_toolkit may not be rendering the toolbar.

- timestamp: 2026-02-13T00:02:00Z
  checked: prompt_toolkit documentation and GitHub issues
  found: Official docs state "the toolbar is always erased when the prompt returns" (from asking_for_input.rst). The bottom_toolbar is rendered "every time the prompt is rendered" but is designed to be temporary.
  implication: This is BY DESIGN. When prompt_async() returns, prompt_toolkit erases the toolbar. It is not displayed during the await _dispatch() period because the prompt session is not active.

## Resolution

root_cause: The toolbar disappears because prompt_toolkit's bottom_toolbar is designed to only display during active prompt sessions. When prompt_async() returns at line 260, prompt_toolkit erases the toolbar. During the subsequent await _dispatch(text) at line 274 (which can take seconds for AI queries or bash commands like sleep 5), no prompt session is active, so no toolbar is rendered. This is documented prompt_toolkit behavior, not a bug in cortex.

fix: Three architectural approaches to solve this:

**Option 1: Run _dispatch() as background task, keep prompt active**
- Instead of awaiting _dispatch() between prompts, create it as a background task
- Keep calling prompt_async() immediately in the loop
- User can type new commands while tasks run in background
- Toolbar stays visible because prompt session never exits
- PROS: Most responsive, matches modern shell UX (zsh with async tasks)
- CONS: Requires rethinking input handling (what if user submits while task running?)

**Option 2: Use Application.run_in_terminal() for task output**
- Keep current sequential model (await _dispatch())
- During task execution, use prompt_toolkit's Application context to render custom UI
- Would need access to the Application object (session.app)
- PROS: Keeps sequential model
- CONS: More complex, need to manage Application lifecycle, may not support background rendering

**Option 3: Print toolbar manually between prompts**
- Before awaiting _dispatch(), print toolbar info using plain print()
- After _dispatch() completes, clear the printed line
- PROS: Simple, no architectural changes
- CONS: Not real-time updates during long tasks, messy with task output

**Recommended: Option 1 (background tasks)**
This matches user expectations for a modern async shell. The task widget shows "2 tasks" exactly when background tasks are running. Current architecture already tracks tasks in self.tasks set. Changes needed:
1. In run() loop: Create _dispatch() as background task instead of awaiting
2. Handle user typing during task execution (buffer input, or queue it)
3. Possibly add command to "wait for tasks" before exit

verification:
files_changed: []
