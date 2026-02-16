---
status: diagnosed
trigger: "Investigate why running a graph via `run ootd(name=\"Dzara\", user_message=\"hi\")` in GRAPH mode locks the REPL input"
created: 2026-02-15T00:00:00Z
updated: 2026-02-15T00:08:00Z
symptoms_prefilled: true
goal: find_root_cause_only
---

## Current Focus

hypothesis: ClaudeCLIBackend subprocess inherits stdin, causing prompt_toolkit to lose access to terminal input while subprocess runs
test: Verified subprocess creation at bae/lm.py:384 - no stdin parameter specified
expecting: stdin inheritance causes terminal input contention between REPL and subprocess
next_action: Confirm this is the root cause by checking if stdin=DEVNULL or stdin=PIPE would fix it

## Symptoms

expected: Graph executes in background, REPL remains responsive for new commands
actual: Graph submits ("submitted g1") but input is blocked until graph completes
errors: None reported, just input blocking
reproduction: Run `run ootd(name="Dzara", user_message="hi")` in GRAPH mode
started: Current behavior (blocking defeats background execution purpose)

## Eliminated

## Evidence

- timestamp: 2026-02-15T00:01:00Z
  checked: ClaudeCLIBackend subprocess creation in bae/lm.py:384-389
  found: subprocess uses stdout=PIPE, stderr=PIPE, but NO stdin parameter specified
  implication: When stdin is not specified, asyncio.create_subprocess_exec inherits stdin from parent process

- timestamp: 2026-02-15T00:02:00Z
  checked: _cmd_run handler in bae/repl/graph_commands.py:43-81
  found: Line 61 calls shell.engine.submit_coro() and line 66 calls shell.engine.submit(), both return immediately after submitting
  implication: The command handler itself is not awaiting the graph - submission is truly fire-and-forget

- timestamp: 2026-02-15T00:03:00Z
  checked: GRAPH mode dispatch in bae/repl/shell.py:418-419
  found: dispatch_graph() is awaited in _dispatch() at line 419
  implication: The await blocks until dispatch_graph returns, but dispatch_graph itself is async and returns after handler completes

- timestamp: 2026-02-15T00:04:00Z
  checked: subprocess creation parameters in bae/lm.py:384-389
  found: start_new_session=True is set, which should create new process group
  implication: start_new_session should detach from controlling terminal, BUT stdin is still inherited if not specified

- timestamp: 2026-02-15T00:05:00Z
  checked: await pattern in bae/lm.py:391-393
  found: process.communicate() is awaited directly after subprocess creation
  implication: The asyncio task BLOCKS on communicate() until subprocess completes, even though it's in event loop

- timestamp: 2026-02-15T00:06:00Z
  checked: stdin handling in subprocess creation
  found: No stdin parameter means subprocess inherits stdin from parent process (the REPL)
  implication: Even with start_new_session=True, the subprocess can still read from parent's stdin if it tries to

- timestamp: 2026-02-15T00:07:00Z
  checked: Workflow in GRAPH mode
  found: User runs `run ootd(...)` → submit_coro → TaskManager background task → coroutine calls LM → subprocess spawned with inherited stdin → subprocess has access to terminal stdin
  implication: Multiple processes (REPL prompt_toolkit AND claude CLI subprocess) competing for same stdin causes blocking

## Resolution

root_cause: |
  ClaudeCLIBackend creates subprocess without stdin parameter (bae/lm.py:384-389).
  When stdin is not specified, asyncio.create_subprocess_exec inherits stdin from the parent process.

  The inheritance chain:
  1. REPL prompt_toolkit owns terminal stdin
  2. Graph task runs in background via TaskManager
  3. Graph makes LM call → ClaudeCLIBackend._run_cli_json()
  4. Subprocess spawned without stdin=... → inherits parent's stdin
  5. Claude CLI subprocess now has access to terminal stdin
  6. prompt_toolkit cannot read from stdin while subprocess holds it
  7. REPL input blocked until subprocess exits (LM call completes)

  Even though start_new_session=True creates a new process group (detaching from job control),
  it does NOT prevent stdin inheritance. The subprocess still shares the same stdin file descriptor
  with the parent process.

  The fix: Add stdin=asyncio.subprocess.DEVNULL to subprocess creation.

fix:
verification:
files_changed: []
