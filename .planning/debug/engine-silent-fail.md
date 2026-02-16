---
status: diagnosed
trigger: "graphs submitted via engine fail immediately with state=FAILED, empty node_timings, no error visibility"
created: 2026-02-15T00:00:00Z
updated: 2026-02-15T00:05:00Z
---

## Current Focus

hypothesis: CONFIRMED -- two bugs, one causal and one compounding
test: complete
expecting: n/a
next_action: return diagnosis

## Symptoms

expected: graph executes nodes, produces node_timings, reaches DONE state
actual: state=FAILED, node_timings=[], current_node='', no error message shown
errors: none visible to user
reproduction: submit graph via GRAPH mode in REPL
started: from initial engine implementation

## Eliminated

## Evidence

- timestamp: 2026-02-15T00:01:00Z
  checked: engine.py _execute method (line 100-115)
  found: |
    _execute passes **kwargs to arun (line 107): `await run.graph.arun(lm=timing_lm, dep_cache=dep_cache, **kwargs)`
    Exception handler (line 113-114) catches Exception, sets FAILED, but re-raises with `raise`.
    However, the exception goes to TaskManager (background task), not to shell output.
  implication: exception is raised but nobody catches/displays it in the REPL

- timestamp: 2026-02-15T00:02:00Z
  checked: shell.py _run_graph method (lines 336-350)
  found: |
    _run_graph calls engine.submit() which returns synchronously (just creates task).
    The try/except only catches errors from submit() itself, not from the async execution.
    The actual graph execution runs as a background task via tm.submit().
  implication: graph execution errors are invisible -- they happen in background task with no error handler

- timestamp: 2026-02-15T00:03:00Z
  checked: shell.py _run_graph (line 343)
  found: |
    `self.engine.submit(graph, self.tm, lm=self._lm, text=text)`
    The `text` variable is the raw user input from the REPL prompt.
    This gets passed as **kwargs to _execute, then to arun.
  implication: arun receives text="user input" as a kwarg

- timestamp: 2026-02-15T00:04:00Z
  checked: graph.py arun method (lines 271-300)
  found: |
    arun signature: `async def arun(self, *, lm=None, max_iters=10, dep_cache=None, **kwargs)`
    Line 300: `missing = set(self._input_fields) - set(kwargs)`
    This checks that all required input fields are present in kwargs.
    But it does NOT check for EXTRA kwargs. Extra kwargs are silently accepted.
    Line 306-307: `start_node = self.start.model_construct(_fields_set=set(kwargs.keys()), **kwargs)`
  implication: text="user input" is passed to model_construct as a field value

- timestamp: 2026-02-15T00:05:00Z
  checked: ootd graph._input_fields
  found: |
    graph._input_fields = {'user_info': FieldInfo(..., required=True), 'user_message': FieldInfo(..., required=True)}
    Engine passes text="..." but graph needs user_info and user_message.
    missing = {'user_info', 'user_message'} -- TypeError raised immediately at arun line 302.
  implication: CONFIRMED -- arun raises TypeError before any node executes

- timestamp: 2026-02-15T00:06:00Z
  checked: engine.py GraphRun dataclass (lines 39-46)
  found: |
    GraphRun has no error/exception field.
    When _execute catches Exception (line 113), it sets state=FAILED and re-raises,
    but the exception object is never stored on the GraphRun.
  implication: even after the fact, engine.get("g1") cannot tell you WHAT failed

- timestamp: 2026-02-15T00:07:00Z
  checked: tasks.py TaskManager._on_done (lines 75-84)
  found: |
    _on_done checks task.exception() to set TaskState.FAILURE, but does not log or
    surface the exception. The exception object stays trapped inside the asyncio.Task.
  implication: exception exists in memory but is never displayed to the user

## Resolution

root_cause: |
  TWO BUGS, one causal and one compounding:

  BUG 1 (Causal) -- Wrong kwarg name:
    shell.py line 343 passes `text=text` to engine.submit().
    This flows through engine._execute (line 107) as **kwargs to graph.arun().
    But the ootd graph's start node (IsTheUserGettingDressed) declares `user_message: str`,
    not `text`. arun() line 300-303 checks for missing required fields and raises
    TypeError("IsTheUserGettingDressed requires: user_info, user_message") immediately,
    before any node executes. Hence: empty node_timings, empty current_node.

  BUG 2 (Compounding) -- Silent error swallowing:
    The TypeError propagates up through engine._execute (line 113-114 sets state=FAILED,
    then re-raises). But _execute runs as a background asyncio.Task via TaskManager.submit().
    Nobody reads that Task's exception. TaskManager._on_done (line 81) notes the failure
    state but does not log it. GraphRun has no error field to store it. The shell's
    _run_graph (line 343) only catches synchronous errors from engine.submit() itself.
    Net result: the user sees "submitted g1" and then... nothing. get("g1") shows
    state=FAILED with zero diagnostics.

fix:
verification:
files_changed: []
