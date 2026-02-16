---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - bae/repl/modes.py
  - bae/repl/shell.py
  - bae/repl/graph_commands.py
  - tests/repl/test_graph_commands.py
  - tests/repl/test_engine.py
  - tests/repl/test_namespace_integration.py
  - tests/repl/test_task_lifecycle.py
autonomous: true
must_haves:
  truths:
    - "Mode.GRAPH no longer exists in the Mode enum"
    - "GRAPH mode no longer appears in mode cycle (Shift+Tab)"
    - "graph_commands.py is deleted"
    - "test_graph_commands.py is deleted"
    - "All remaining tests pass"
  artifacts:
    - path: "bae/repl/modes.py"
      provides: "Mode enum without GRAPH"
    - path: "bae/repl/shell.py"
      provides: "Shell dispatch without GRAPH branch"
  key_links: []
---

<objective>
Remove GRAPH mode from the REPL entirely: the Mode enum entry, the mode cycle, the dispatch branch in shell.py, the graph_commands.py module, and test_graph_commands.py.

Purpose: GRAPH mode is being removed.
Output: Clean codebase with no GRAPH mode references in runtime code or tests.
</objective>

<execution_context>
@/Users/dzaramelcone/.claude/get-shit-done/workflows/execute-plan.md
@/Users/dzaramelcone/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@bae/repl/modes.py
@bae/repl/shell.py
@bae/repl/graph_commands.py
@tests/repl/test_graph_commands.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove GRAPH mode from modes.py and shell.py</name>
  <files>
    bae/repl/modes.py
    bae/repl/shell.py
    bae/repl/graph_commands.py
  </files>
  <action>
1. In `bae/repl/modes.py`:
   - Remove `GRAPH = "GRAPH"` from Mode enum
   - Remove `Mode.GRAPH` entry from MODE_COLORS
   - Remove `Mode.GRAPH` entry from MODE_NAMES
   - Remove `Mode.GRAPH` from MODE_CYCLE list

2. In `bae/repl/shell.py`:
   - Remove `from bae.repl.graph_commands import dispatch_graph` import
   - Remove `from bae.repl.graph_commands import _make_notify` import (line 260)
   - Remove the entire `elif self.mode == Mode.GRAPH:` block in `_dispatch` (lines 468-474, the shush handling and dispatch_graph call)
   - Remove the `_graph_ctx.set(...)` call and its related imports (lines 258-262) -- but keep `self.engine = GraphRegistry()` since the engine is still used for programmatic graph submission
   - Remove `self.shush_gates` attribute from __init__ (line 246)
   - In `_dispatch`, the `@g` gate routing condition currently checks `self.mode != Mode.NL` -- update to check `self.mode in (Mode.PY, Mode.BASH)` since GRAPH no longer exists
   - Keep `channel_arun`, `self.engine`, and `self.namespace["engine"]` -- those are for programmatic graph execution, not GRAPH mode
   - Keep the `_make_notify` usage if still needed by `_graph_ctx.set` -- actually, remove the whole `_graph_ctx.set` block since it was specifically for GRAPH mode auto-registration. If `_graph_ctx` is used elsewhere for programmatic graph submission, keep it but re-import `_make_notify` differently.

   Actually, re-check: `_graph_ctx` is set once in `__init__` and provides the engine/tm/lm/notify for auto-registration of graphs created inside the REPL. This supports `run mygraph(...)` in GRAPH mode. Since GRAPH mode is going away, check if anything else reads `_graph_ctx`. If only graph_commands.py does, remove the `_graph_ctx.set()` call. If engine.py reads it for auto-registration (the `graph()` factory uses it), keep it but build the notify differently -- use a simple lambda that writes to the router instead of `_make_notify`.

3. Delete `bae/repl/graph_commands.py` entirely.
  </action>
  <verify>
    `python -c "from bae.repl.modes import Mode, MODE_CYCLE; assert not hasattr(Mode, 'GRAPH'); assert len(MODE_CYCLE) == 3"`
    `python -c "from bae.repl.shell import CortexShell"` (import succeeds)
  </verify>
  <done>Mode.GRAPH does not exist, shell.py imports cleanly, graph_commands.py is deleted, mode cycle has 3 modes (NL, PY, BASH).</done>
</task>

<task type="auto">
  <name>Task 2: Remove GRAPH mode tests, fix remaining test references</name>
  <files>
    tests/repl/test_graph_commands.py
    tests/repl/test_engine.py
    tests/repl/test_namespace_integration.py
    tests/repl/test_task_lifecycle.py
  </files>
  <action>
1. Delete `tests/repl/test_graph_commands.py` entirely.

2. In `tests/repl/test_engine.py`:
   - The `mode="GRAPH"` strings in fake notify callbacks (lines ~919, 972, 1032) are just metadata strings passed to a FakeRouter -- they don't reference Mode.GRAPH. These can stay as-is since they're just string labels, OR change them to a neutral string if Dzara prefers clean removal. Leave as-is -- they're engine tests, not mode tests.

3. In `tests/repl/test_namespace_integration.py`:
   - Lines 128-155 contain comments saying "Simulating GRAPH mode" -- update these comments to say "Simulating graph engine" or similar. The actual code doesn't import Mode.GRAPH, just references the concept in docstrings/comments.

4. In `tests/repl/test_task_lifecycle.py`:
   - Line 310 mentions "NL/GRAPH/BASH" in a docstring -- update to "NL/BASH".

5. Run the full test suite: `uv run pytest tests/ -x -q --ignore=tests/test_integration.py` and fix any failures.
  </action>
  <verify>`uv run pytest tests/ -x -q --ignore=tests/test_integration.py` -- all tests pass with clean output.</verify>
  <done>test_graph_commands.py deleted, no references to GRAPH mode in remaining test docstrings/comments, all tests pass.</done>
</task>

</tasks>

<verification>
- `grep -r "Mode.GRAPH" bae/` returns no results
- `grep -r "graph_commands" bae/` returns no results
- `grep -r "dispatch_graph" bae/` returns no results
- `ls bae/repl/graph_commands.py` fails (file deleted)
- `ls tests/repl/test_graph_commands.py` fails (file deleted)
- `uv run pytest tests/ -x -q --ignore=tests/test_integration.py` passes
</verification>

<success_criteria>
- GRAPH removed from Mode enum and mode cycle
- graph_commands.py and test_graph_commands.py deleted
- Shell dispatch no longer has GRAPH branch
- All remaining tests pass cleanly
</success_criteria>

<output>
After completion, create `.planning/quick/1-remove-graph-mode-and-all-associated-tes/1-SUMMARY.md`
</output>
