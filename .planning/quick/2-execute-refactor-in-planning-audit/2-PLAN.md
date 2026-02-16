---
phase: quick-2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - bae/graph.py
  - bae/lm.py
  - bae/resolver.py
  - bae/work/prompt.py
  - bae/repl/shell.py
  - bae/repl/engine.py
  - bae/cli.py
  - bae/node.py
  - bae/work/deps.py
autonomous: true
must_haves:
  truths:
    - "All existing tests pass with zero regressions (647 passed)"
    - "No duplicate function implementations remain across modules"
    - "Long functions are decomposed into focused helpers"
    - "Boilerplate gate functions use factory pattern"
  artifacts:
    - path: "bae/graph.py"
      provides: "Shared _get_base_type with union handling, inlined trivials"
    - path: "bae/lm.py"
      provides: "Imports _get_base_type from graph.py, split transform_schema"
    - path: "bae/resolver.py"
      provides: "Unified DAG walk, split _resolve_one"
    - path: "bae/work/prompt.py"
      provides: "Factory-generated gate functions and aliases"
    - path: "bae/repl/engine.py"
      provides: "Shared lifecycle context manager, TimingLM._timed helper"
    - path: "bae/repl/shell.py"
      provides: "Merged coroutine walker, extracted _run_py, split key bindings"
  key_links:
    - from: "bae/lm.py"
      to: "bae/graph.py"
      via: "import _get_base_type"
      pattern: "from bae\\.graph import _get_base_type"
    - from: "bae/resolver.py"
      to: "bae/resolver.py"
      via: "_walk_dep_hints shared by both DAG builders"
      pattern: "def _walk_dep_hints"
---

<objective>
Execute all 8 priorities from codebase-cleanup.md audit as a single refactoring plan.

Purpose: Eliminate duplication, reduce function sizes, collapse boilerplate -- all with zero test regressions.
Output: Cleaner codebase, same behavior.
</objective>

<execution_context>
@/Users/dzaramelcone/.claude/get-shit-done/workflows/execute-plan.md
@/Users/dzaramelcone/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/audit/codebase-cleanup.md
@bae/graph.py
@bae/lm.py
@bae/resolver.py
@bae/work/prompt.py
@bae/repl/shell.py
@bae/repl/engine.py
@bae/cli.py
@bae/node.py
@bae/work/deps.py
@bae/work/models.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Deduplicate shared logic (P1, P2, P3, P6, P7)</name>
  <files>
    bae/graph.py
    bae/lm.py
    bae/resolver.py
    bae/work/prompt.py
    bae/repl/shell.py
  </files>
  <action>
Five deduplication changes. Run tests after each sub-change.

**P1 -- Consolidate `_get_base_type()`:**
- Keep the richer version in `bae/graph.py` (lines 25-43) which handles both Annotated unwrap AND union types (X | None).
- In `bae/lm.py`: delete the local `_get_base_type` (lines 121-125), add `from bae.graph import _get_base_type` at the top imports.
- Verify: `_get_base_type` is only called at lm.py:144 and graph.py:431 area. Both callers work with the richer version.

**P2 -- Unify resolver DAG walks:**
- `build_dep_dag()` (line 141) and `_build_fn_dag()` (line 326) share an identical inner `walk()` function. Extract a shared helper `_walk_dep_hints(ts, visited, fn)` that does the recursive walk (lines 158-183 pattern). Both `build_dep_dag` and `_build_fn_dag` create the TopologicalSorter and visited set, then call `_walk_dep_hints` for the walk.
- `build_dep_dag` seeds by iterating node_cls fields and calling `_walk_dep_hints` for each dep target found (current lines 186-198).
- `_build_fn_dag` seeds by calling `_walk_dep_hints(ts, visited, fn)` directly (current line 367).
- Split `_resolve_one()` (line 273, 51 lines) into two functions: `_resolve_node_dep(fn, cache, trace)` for the Node-as-Dep path (lines 291-296) and `_resolve_callable_dep(fn, cache, trace)` for the regular callable path (lines 298-323). Keep `_resolve_one` as a thin dispatcher that checks `_is_node_type(fn)` and delegates.

**P3 -- Collapse prompt.py gate boilerplate:**
- Replace the seven gate functions (confirm_continue through confirm_brownfield) with a factory:
  ```python
  def _gate(msg: str):
      async def gate(prompt: PromptDep) -> bool:
          return await prompt.confirm(msg)
      return gate
  ```
- Generate all seven from a dict mapping name -> message string.
- Generate the seven `Annotated[bool, Dep(...)]` aliases from the same dict.
- The factory-generated functions MUST have `__name__` set to the original name (e.g., `gate.__name__ = "confirm_continue"`) because resolver uses `_callable_name()` for error messages and the dep DAG uses function identity.
- Also set `__qualname__` and `__module__` for clean tracebacks.
- Keep the docstrings by setting `gate.__doc__` from the dict as well.

**P6 -- Merge coroutine walk functions:**
- `_contains_coroutines()` (shell.py:52-71) and `_count_and_close_coroutines()` (shell.py:74-93) share identical traversal. Merge into one function `_walk_coroutines(obj, close=False, _seen=None)` that:
  - When `close=False`: returns True/False (contains check) -- same as `_contains_coroutines`
  - When `close=True`: returns int count, closes each found -- same as `_count_and_close_coroutines`
- Update callers in `_dispatch()` (shell.py lines 423-424 and 443-444):
  - `_contains_coroutines(val)` -> `_walk_coroutines(val)`
  - `_count_and_close_coroutines(val)` -> `_walk_coroutines(val, close=True)`

**P7 -- Inline trivial abstractions:**
- `_build_context()` (graph.py:46-52): called once at line 431. Inline the dict comprehension at the call site, delete the function.
- `_build_instruction()` (graph.py:55-57): called at lines 408 and 441. Replace with `target_type.__name__` at each call site, delete the function.
  </action>
  <verify>
Run `uv run pytest tests/ -x -q --ignore=tests/test_integration.py` -- all 647 tests pass, 5 skipped, zero failures.
Grep to confirm no remaining duplicate: `grep -rn "def _get_base_type" bae/` shows exactly 1 hit (graph.py).
Grep: `grep -rn "def _build_context\|def _build_instruction" bae/graph.py` shows zero hits.
  </verify>
  <done>
No duplicate `_get_base_type` across modules. Resolver has one shared walk helper. Prompt gates use factory. Coroutine walkers merged. Trivial abstractions inlined. All tests green.
  </done>
</task>

<task type="auto">
  <name>Task 2: Break up long functions and deduplicate engine lifecycle (P4, P5)</name>
  <files>
    bae/repl/shell.py
    bae/repl/engine.py
    bae/lm.py
  </files>
  <action>
Three refactors targeting long functions. Run tests after each sub-change.

**P4a -- Split `_build_key_bindings()` (shell.py, 102 lines):**
Extract three focused binding-registration helpers that each take `kb` and `shell`:
- `_bind_mode_controls(kb, shell)` -- shift-tab cycle, ctrl-v view cycle, enter submit, escape-enter newline, ctrl-o channel toggle
- `_bind_interrupt(kb, shell)` -- ctrl-c handler with idle/kill-all/task-menu logic
- `_bind_task_menu(kb, shell)` -- escape dismiss, left/right page, digit cancel (needs the `task_menu_active` Condition, create inside this helper)
Then `_build_key_bindings` becomes: create kb, call the three helpers, return kb. The `task_menu_active` Condition must be created inside `_bind_task_menu` (or passed in) since it references `shell._task_menu`.

**P4b -- Extract `_run_py()` from `_dispatch()` (shell.py, 78 lines):**
Extract the PY mode block (lines 410-456) into `async def _run_py(self, text)`. The `_dispatch` method becomes a clean three-way branch: PY calls `_run_py`, NL submits task, BASH submits task. Keep the gate input check at the top of `_dispatch`.

**P4c -- Split `transform_schema()` (lm.py, 77 lines):**
Extract helpers by schema type:
- `_transform_object(schema, strict)` -- handles properties, additionalProperties, required
- `_transform_array(schema, strict)` -- handles items, minItems
- `_transform_string(schema, strict)` -- handles format
The main `transform_schema` handles refs, $defs, anyOf/oneOf/allOf, type dispatch, and the leftover-to-description fold.

**P5 -- Deduplicate engine.py lifecycle:**
`_execute()` (line 214) and `_wrap_coro()` (line 313) share identical: _emit closure, _dep_timing_hook closure, log handler attach/detach, RSS measurement, state transitions, notify calls.

Extract an async context manager `_lifecycle(self, run, *, notify, policy)` that:
1. Sets `run.policy = policy`
2. Creates `_emit` and `_dep_timing_hook` closures
3. Attaches log handler if VERBOSE
4. On `__aenter__`: emits start event, records `rss_before`, returns a context object with `_emit`, `_dep_timing_hook`
5. On `__aexit__`: handles DONE/CANCELLED/FAILED state transitions, RSS delta, elapsed time emit, log handler cleanup, archive

Then `_execute` becomes: `async with self._lifecycle(run, ...) as ctx:` + the actual graph execution logic (build dep_cache with ctx.dep_timing_hook, run graph, set run.result).
And `_wrap_coro` becomes: `async with self._lifecycle(run, ...) as ctx:` + set contextvar token + `await coro` + set run.result.

The differences between the two methods:
- `_execute` builds dep_cache with LM/gate/timing and calls `run.graph.arun()`
- `_wrap_coro` sets `_engine_dep_cache` contextvar token and awaits the raw coro
- `_execute` always sets `run.result = result`
- `_wrap_coro` only sets `run.result = result` if `hasattr(result, "trace")`

Handle these differences in the caller code after the context manager, not in the context manager itself.

**P8c -- TimingLM._timed helper (engine.py):**
`fill()` (139-147) and `make()` (152-160) in TimingLM duplicate timing wrap. Extract:
```python
async def _timed(self, method, *args, node_name, **kwargs):
    start = time.perf_counter_ns()
    result = await method(*args, **kwargs)
    end = time.perf_counter_ns()
    self._run.current_node = node_name
    self._run.node_timings.append(NodeTiming(node_type=node_name, start_ns=start, end_ns=end))
    return result
```
Then `fill` becomes `return await self._timed(self._inner.fill, target, resolved, instruction, source, node_name=target.__name__)` and similarly for `make`.
  </action>
  <verify>
Run `uv run pytest tests/ -x -q --ignore=tests/test_integration.py` -- all 647 tests pass, 5 skipped, zero failures.
Confirm `_build_key_bindings` body is under 15 lines.
Confirm `_dispatch` body is under 30 lines.
Confirm `_execute` and `_wrap_coro` each under 20 lines (excluding the shared lifecycle).
  </verify>
  <done>
Long functions decomposed. Engine lifecycle deduplicated via context manager. TimingLM uses shared _timed helper. All tests green.
  </done>
</task>

<task type="auto">
  <name>Task 3: Minor cleanup (P8 remaining items)</name>
  <files>
    bae/cli.py
    bae/node.py
    bae/work/deps.py
  </files>
  <action>
Small targeted fixes. Run tests after each.

**P8a -- Remove duplicate import in cli.py:**
- Line 242 has `import json` inside the `run` function body, but `json` is already imported at line 13 (module level). Delete the local import at line 242.

**P8b -- Clean up Node.__call__ signature (node.py:194):**
- `__call__` accepts `*_args, **_kwargs` that are never passed by graph.py (the only caller). Remove the extra params. New signature: `async def __call__(self, lm: LM) -> Node | None`.
- Verify no subclass in the codebase passes extra args by grepping for `super().__call__` and `.__call__(` patterns.

**P8d -- Annotate work/deps.py stubs:**
- `scan_secrets()` (line 68) and `detect_brownfield()` (line 106) are stubs. These are already clearly marked with `# Stub` comments. No code change needed -- the audit just flags them for awareness. Skip these.

Note: P8 items about `work/models.py` typing (`list[dict]` -> typed, `str` -> Enum) are NOT included -- those are type-narrowing changes that could break Recall resolution or serialization and are better done as a separate, deliberate change. The audit lists them as "could be" not "must be".

Note: P8 `repl/exec.py:_ensure_cortex_module()` thread-safety note is acknowledged as acceptable for single-process REPL. No change needed.
  </action>
  <verify>
Run `uv run pytest tests/ -x -q --ignore=tests/test_integration.py` -- all 647 tests pass, 5 skipped, zero failures.
Grep: `grep -n "import json" bae/cli.py` shows exactly 1 hit (line 13).
Grep: `grep -n "__call__" bae/node.py` shows clean signature without *_args/**_kwargs.
  </verify>
  <done>
Duplicate import removed. Node.__call__ signature cleaned. All tests green. Audit fully addressed.
  </done>
</task>

</tasks>

<verification>
After all three tasks complete:
1. `uv run pytest tests/ -x -q --ignore=tests/test_integration.py` -- 647 passed, 5 skipped
2. No function appears in more than one module with the same name and purpose
3. No function exceeds ~60 lines
4. Gate boilerplate in prompt.py is factory-generated
5. `git diff --stat` shows only the listed files modified
</verification>

<success_criteria>
All 8 audit priorities addressed (or explicitly deferred with rationale for models.py typing).
Zero test regressions. Clean git diff touching only the files listed.
</success_criteria>

<output>
After completion, create `.planning/quick/2-execute-refactor-in-planning-audit/2-SUMMARY.md`
</output>
