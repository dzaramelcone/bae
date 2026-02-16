# Codebase Cleanup Audit

Date: 2026-02-15
Scope: All .py files under bae/ (excluding tests/, examples/, .planning/)

```xml
<assumptions>
  <assumption claim="bae/work/ graphs are representative of intended design patterns" risk="low - they're the only concrete work graphs in the codebase"/>
  <assumption claim="netflix/dispatch style means: flat modules, domain grouping, no scattered utils, clear single-responsibility" risk="low - standard interpretation"/>
  <assumption claim="REPL code is in-scope despite being a separate concern from the graph engine" risk="medium - REPL is large and may have its own cleanup cadence"/>
  <assumption claim="Stubs in work/deps.py are intentionally deferred, not forgotten" risk="medium - scan_secrets() and detect_brownfield() return hardcoded values"/>
</assumptions>

<reasoning>
I read every .py file under bae/ and categorized findings by severity and theme.
The codebase has a clean core (node.py, markers.py, exceptions.py, result.py, agent.py)
but accumulates debt in three zones:

1. **Scattered shared utilities** -- _unwrap_annotated(), _get_base_type(), and
   strip-regex patterns are reimplemented across 3+ files. There's no shared
   location, so each file grows its own copy.

2. **resolver.py** -- The most complex module. build_dep_dag() and the DAG walk
   inside resolve_fields() are near-duplicates. _resolve_one() is 50 lines doing
   two jobs (Node-as-Dep vs callable-Dep).

3. **REPL shell.py** -- _build_key_bindings() is 102 lines of nested closures.
   _dispatch() mixes PY/NL/GRAPH/BASH concerns in one long method.
   _contains_coroutines() and _count_and_close_coroutines() walk the same
   structure with identical logic.

4. **Trivial abstractions** -- _build_context() and _build_instruction() in graph.py
   are 1-liners that add indirection without value. Seven gate functions in
   work/prompt.py differ only in their prompt string.

5. **Overly broad catches** -- graph.py:345, repl/engine.py:117, repl/tasks.py:90
   all catch bare Exception or (ProcessLookupError, OSError) without documenting why.

6. **work/prompt.py boilerplate** -- Seven confirm_* functions and their Annotated
   aliases are copy-paste with different strings. A factory or registry would
   collapse them.
</reasoning>

<answer>
## Priority 1: Consolidate duplicated utilities

**Scattered helpers** -- Create `bae/_typing.py` (or similar):
- `_unwrap_annotated()` -- currently in node.py:81 AND graph.py:18
- `_get_base_type()` -- currently in lm.py:121 AND graph.py:25 (identical logic)
- `_extract_types_from_hint()` -- node.py:88, partially reimplemented in graph.py

**Strip regexes** -- `_STRIP_WRITE_RE`, `_STRIP_RUN_RE`, `_STRIP_EDIT_RE` defined in
both `repl/ai.py` and `repl/views.py`. Extract to `repl/_patterns.py`.

## Priority 2: Deduplicate resolver.py

- `build_dep_dag()` (line 128) and the DAG walk inside `resolve_fields()` (line 402)
  share the same topo-sort-then-gather pattern. Extract the common walk.
- `_resolve_one()` (line 260, 50 lines) does two distinct jobs: Node-as-Dep resolution
  and callable-Dep resolution. Split into two functions.

## Priority 3: Collapse work/prompt.py boilerplate

Seven gate functions (`confirm_continue`, `confirm_refresh`, `confirm_commit`, etc.)
differ only in their prompt string. Replace with:
```python
def _gate(msg: str) -> Callable:
    async def gate(prompt: Prompt) -> bool:
        return await prompt.confirm(msg)
    return gate

confirm_continue = _gate("Continue to next phase?")
# ... etc
```

Same for the seven `Annotated[bool, Dep(...)]` aliases -- generate from a dict.

## Priority 4: Break up long functions

| Function | Lines | Fix |
|----------|-------|-----|
| `repl/shell.py:_build_key_bindings()` | 102 | Split by concern (mode toggle, task menu, interrupt) |
| `repl/shell.py:_dispatch()` | 45 | Extract `_run_py()` for PY mode |
| `resolver.py:resolve_fields()` | 76 | Extract topo-sort-and-gather |
| `repl/graph_commands.py:_cmd_inspect()` | 56 | Extract timing lookup helper |
| `lm.py:transform_schema()` | 77 | Split by schema type (object/array/string) |

## Priority 5: Inline trivial abstractions

- `graph.py:_build_context()` (line 46) -- 1-liner dict comprehension, inline at call site
- `graph.py:_build_instruction()` (line 55) -- returns `target_type.__name__`, inline it

## Priority 6: Tighten exception handling

- `graph.py:345` -- catches bare `Exception`, converts to `DepError`. Catch specific dep failures.
- `repl/engine.py:117` -- catches `Exception` in `_execute()`. Should distinguish graph errors from system errors.
- `repl/shell.py:_contains_coroutines()` and `_count_and_close_coroutines()` -- same walk logic, merge into one function with a callback.

## Priority 7: Minor cleanup

- `cli.py:242` -- duplicate `import json` (already at line 13)
- `repl/engine.py:TimingLM` -- `fill()` and `make()` duplicate timing logic; extract to decorator or wrapper
- `repl/graph_commands.py` -- timing_map construction duplicated between `_cmd_inspect()` and `_cmd_trace()`
- `node.py:191` -- `__call__` accepts `*_args, **_kwargs` that are never passed; remove
- `work/models.py:RoadmapData.phases` is `list[dict]` -- should be a typed model
</answer>

<completeness_check>
Covered: all 34 .py files under bae/, including repl/, work/, and root modules.
NOT covered: tests/ (out of scope per instructions), examples/, .planning/.
Edge cases checked: import chains (no circular deps from consolidation),
REPL's extract_executable dependency (confirmed intact after agent.py cleanup).
Missing from audit: performance characteristics, async safety of shared state
in repl/exec.py (_ensure_cortex_module modifies sys.modules globally).
</completeness_check>

<confidence>0.80 - High coverage of source files but some REPL modules were only
partially read by the subagent (channels.py, store.py, toolbar.py). The core
engine findings (resolver, graph, lm, node) are solid. Work graph findings
are directional -- the stubs may be intentionally deferred.</confidence>
```

## Per-file detail

### Clean files (no action needed)

| File | Notes |
|------|-------|
| `bae/__init__.py` | Clean exports |
| `bae/markers.py` | Minimal, correct |
| `bae/exceptions.py` | Good inheritance, cause chaining |
| `bae/result.py` | Clean generic |
| `bae/agent.py` | Single function after AgenticBackend removal |
| `bae/work/__init__.py` | Clean exports |
| `bae/work/execute_phase.py` | Clean node graph |
| `bae/work/plan_phase.py` | Clean node graph |
| `bae/work/quick.py` | Simple, correct |
| `bae/repl/__init__.py` | Clean |

### Files with findings

#### bae/cli.py
- Line 242: duplicate `import json` (already at line 13)
- Lines 130-138 vs 168-169: `_encode_mermaid_for_live()` call pattern duplicated between `graph_show()` and `graph_export()`
- Lines 170-206: `graph_export()` doesn't validate output path writability or create parent dirs

#### bae/graph.py
- Lines 25-43: `_get_base_type()` duplicates `lm.py:121-125`
- Lines 46-52: `_build_context()` is a 1-liner dict comprehension; inline it
- Lines 55-57: `_build_instruction()` just returns `target_type.__name__`; inline it
- Lines 339-352: bare `Exception` catch converted to `DepError`
- Lines 381-403: duplicate field resolution logic between custom-call and ellipsis paths
- Lines 416-444: ellipsis routing branch is 28 lines of nested logic
- Lines 489-543: `graph()` wrapper is long and stateful

#### bae/node.py
- Lines 81-85: `_unwrap_annotated()` duplicated in graph.py:18
- Lines 88-111: `_extract_types_from_hint()` partially reimplemented in graph.py
- Lines 191-204: `__call__` accepts `*_args, **_kwargs` never passed by graph.py

#### bae/lm.py
- Lines 33-110: `transform_schema()` is 77 lines; split by schema type
- Lines 121-125: `_get_base_type()` duplicated in graph.py:25-43

#### bae/resolver.py
- Lines 128-187 vs 313-355: `build_dep_dag()` and `_build_fn_dag()` near-identical walk
- Lines 260-310: `_resolve_one()` is 50 lines doing two jobs
- Lines 402-478: `resolve_fields()` duplicates topo-sort-and-gather from `resolve_dep()`
- Lines 467-476: walks hints a third time to build resolved dict

#### bae/work/deps.py
- Lines 68-71: `scan_secrets()` is a stub returning hardcoded `clean=True`
- Lines 106-109: `detect_brownfield()` is a stub returning empty result
- Lines 112-120: Annotated dep aliases inconsistent (some have defaults, some don't)

#### bae/work/models.py
- Lines 16-18: `RoadmapData.phases` is `list[dict]` -- should be typed
- Lines 10-13: `ProjectState.status` is a bare string -- should be Enum

#### bae/work/prompt.py
- Lines 79-111: 7 gate functions differ only in prompt string -- use factory
- Lines 114-120: 7 Annotated gate aliases -- generate from dict

#### bae/work/new_project.py
- Lines 92-108: `save_project_roadmap()` accesses deep nested attrs without null checks
- Lines 200-210: magic strings `["no", "n", "done", ""]` for input validation

#### bae/work/map_codebase.py
- Lines 53-61: `map_one()` closure creates its own Graph and LM; signature looks suspicious

#### bae/repl/shell.py
- Lines 52-94: `_contains_coroutines()` and `_count_and_close_coroutines()` duplicate walk logic
- Lines 113-215: `_build_key_bindings()` is 102 lines of nested closures
- Lines 362-406: `_dispatch()` mixes PY/NL/GRAPH/BASH in 45 lines
- Lines 324-351: `_run_nl()` and `_run_bash()` duplicate error handling

#### bae/repl/engine.py
- Lines 52-84: `TimingLM` duplicates timing logic between `fill()` and `make()`
- Lines 103-126 vs 146-166: `_execute()` and `_wrap_coro()` duplicate error handling

#### bae/repl/views.py
- Lines 42-59: strip regexes duplicated from ai.py
- Lines 112-133: `_render_grouped_panel()` and `_render_code_panel()` nearly identical

#### bae/repl/graph_commands.py
- Lines 157-214 vs 232-234: timing_map building duplicated between `_cmd_inspect()` and `_cmd_trace()`
- Lines 85-106: string-based task name matching is fragile

#### bae/repl/ai.py
- Lines 37-46: `_STRIP_*` regex patterns duplicated from views.py

#### bae/repl/exec.py
- Lines 14-25: `_ensure_cortex_module()` modifies `sys.modules` globally; not thread-safe
