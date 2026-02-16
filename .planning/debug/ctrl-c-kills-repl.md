---
status: diagnosed
trigger: "Ctrl-C kills entire REPL instead of showing task menu when graph is running"
created: 2026-02-15T00:00:00Z
updated: 2026-02-15T00:00:00Z
---

## Current Focus

hypothesis: ClaudeCLIBackend._run_cli_json spawns subprocesses WITHOUT start_new_session=True, so child inherits REPL's process group and receives SIGINT directly from the terminal
test: compare subprocess creation across ai.py, bash.py, agent.py vs lm.py
expecting: lm.py missing start_new_session=True
next_action: return diagnosis

## Symptoms

expected: Ctrl-C while graph task running should open task menu (key binding in shell.py line 153)
actual: Ctrl-C kills entire REPL process
errors: REPL exits to shell
reproduction: submit graph in GRAPH mode, press Ctrl-C
started: likely since graph execution was added

## Eliminated

(none needed - root cause found on first hypothesis)

## Evidence

- timestamp: 2026-02-15T00:01:00Z
  checked: shell.py Ctrl-C key binding (line 153-169)
  found: prompt_toolkit key binding properly checks active tasks and opens menu
  implication: the key binding never fires because SIGINT kills the process before prompt_toolkit can intercept it

- timestamp: 2026-02-15T00:02:00Z
  checked: lm.py ClaudeCLIBackend._run_cli_json (line 464-468)
  found: subprocess created WITHOUT start_new_session=True
  implication: child process inherits REPL's process group; terminal SIGINT goes to both REPL and child

- timestamp: 2026-02-15T00:03:00Z
  checked: ai.py subprocess creation (line 229-236)
  found: uses start_new_session=True
  implication: AI subprocess is isolated from REPL's process group - SIGINT works correctly for AI tasks

- timestamp: 2026-02-15T00:04:00Z
  checked: bash.py subprocess creation (line 28-35)
  found: uses start_new_session=True
  implication: bash subprocess is isolated from REPL's process group - SIGINT works correctly for bash tasks

- timestamp: 2026-02-15T00:05:00Z
  checked: agent.py subprocess creation (line 167-174)
  found: uses start_new_session=True
  implication: agent subprocess is isolated - consistent with ai.py and bash.py

- timestamp: 2026-02-15T00:06:00Z
  checked: engine.py GraphRegistry._execute (line 100-118)
  found: calls graph.arun() which calls LM.fill()/choose_type()/decide(), which call _run_cli_json()
  implication: every LM call during graph execution spawns a subprocess in the REPL's process group

- timestamp: 2026-02-15T00:07:00Z
  checked: lm.py _run_cli_json CancelledError handler (line 477-480)
  found: handles CancelledError by killing process, but this is moot - SIGINT kills REPL before cancellation can happen
  implication: the CancelledError path is unreachable in the SIGINT scenario because the REPL is already dead

## Resolution

root_cause: |
  ClaudeCLIBackend._run_cli_json() at bae/lm.py:464 creates subprocesses
  WITHOUT start_new_session=True. This means the child process inherits the
  REPL's process group. When the user presses Ctrl-C, the terminal sends
  SIGINT to the entire foreground process group, which includes both the REPL
  and the Claude CLI subprocess. The REPL's Python process receives SIGINT and
  raises KeyboardInterrupt before prompt_toolkit's key binding handler (which
  intercepts Ctrl-C at the terminal input level) can process it.

  Every other subprocess in the codebase (ai.py:235, bash.py:34, agent.py:173)
  uses start_new_session=True to isolate the child into its own process group.
  lm.py is the sole outlier.

fix: (not applied - diagnosis only)
verification: (not applied - diagnosis only)
files_changed: []
