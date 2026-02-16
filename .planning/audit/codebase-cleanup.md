# Codebase Cleanup Audit

Date: 2026-02-15 (revised 2026-02-15)
Scope: All 33 .py files under bae/ (excluding tests/, examples/, .planning/)

## Summary

The codebase has a clean core (node.py, markers.py, exceptions.py, result.py, agent.py)
and clean work graphs (execute_phase.py, plan_phase.py, quick.py, new_project.py, map_codebase.py).
Debt concentrates in three zones:

1. **`_get_base_type()` duplication** -- lm.py:121 and graph.py:25 implement the same
   Annotated-unwrap logic but graph.py's version also handles union types. These
   should converge.

2. **resolver.py structural duplication** -- `build_dep_dag()` and `_build_fn_dag()`
   share an identical walk pattern. `_resolve_one()` does two jobs. `_execute()` and
   `_wrap_coro()` in engine.py duplicate lifecycle boilerplate.

3. **REPL shell.py** -- `_build_key_bindings()` is 102 lines. `_dispatch()` is 78 lines
   mixing PY/NL/BASH. Coroutine walk functions duplicate traversal logic.

4. **work/prompt.py boilerplate** -- Seven gate functions and seven Annotated aliases
   differ only in their prompt string.

## Priority 1: Consolidate `_get_base_type()`

- `lm.py:121-125` -- simple Annotated unwrap
- `graph.py:25-43` -- Annotated unwrap + union (X | None) handling

These are genuine duplicates with slight divergence. Converge into one shared function.

Note: `_unwrap_annotated()` (node.py:81) is NOT duplicated -- graph.py:18 imports it.
Note: `_extract_types_from_hint()` (node.py:88) is NOT reimplemented in graph.py --
graph.py's `_get_routing_strategy()` does different work (strategy routing, not type extraction).

## Priority 2: Deduplicate resolver.py

- `build_dep_dag()` (line 141) and `_build_fn_dag()` (line 326) are near-identical
  TopologicalSorter-building walks. `build_dep_dag` seeds from a node class's fields,
  `_build_fn_dag` seeds from a single callable. Unify with a shared walk + different
  seed logic.
- `_resolve_one()` (line 273, 51 lines) does two jobs: Node-as-Dep resolution
  (lines 291-296) and callable-Dep resolution (lines 298-323). Split into two functions.

## Priority 3: Collapse work/prompt.py boilerplate

Seven gate functions (`confirm_continue`, `confirm_refresh`, `confirm_secrets`,
`confirm_failures`, `confirm_blockers`, `confirm_approve`, `confirm_brownfield`)
differ only in their prompt string. Replace with factory:
```python
def _gate(msg: str):
    async def gate(prompt: PromptDep) -> bool:
        return await prompt.confirm(msg)
    return gate

confirm_continue = _gate("Continue?")
```

Same for the seven `Annotated[bool, Dep(...)]` aliases -- generate from a dict.

## Priority 4: Break up long functions

| Function | Lines | Fix |
|----------|-------|-----|
| `repl/shell.py:_build_key_bindings()` | 102 (113-215) | Split by concern (mode toggle, task menu, interrupt) |
| `repl/shell.py:_dispatch()` | 78 (392-469) | Extract `_run_py()` for PY mode (sync + async paths) |
| `lm.py:transform_schema()` | 77 (33-110) | Split by schema type (object/array/string) |
| `repl/engine.py:_execute()` | 70 (214-288) | See Priority 5 |

## Priority 5: Deduplicate engine.py lifecycle

`_execute()` (line 214) and `_wrap_coro()` (line 313) share identical:
- `_emit()` closure setup
- `_dep_timing_hook()` closure
- log handler attach/detach
- RSS measurement
- state transitions (DONE/CANCELLED/FAILED)
- notify calls for start/complete/fail/cancel

Extract a shared lifecycle context manager or helper.

## Priority 6: Merge coroutine walk functions

`_contains_coroutines()` (shell.py:52-71) and `_count_and_close_coroutines()` (shell.py:74-93)
traverse the same data structures with identical recursion. Merge into one walk with
a mode parameter or callback.

## Priority 7: Inline trivial abstractions

- `graph.py:_build_context()` (line 46) -- dict comprehension over model_fields, called
  once at line 431. Inline at call site.
- `graph.py:_build_instruction()` (line 55) -- returns `target_type.__name__`, called at
  lines 408, 441. Inline both.

## Priority 8: Minor cleanup

- `cli.py:242` -- duplicate `import json` (already at line 13)
- `node.py:194` -- `__call__` accepts `*_args, **_kwargs` never passed by graph.py
- `repl/engine.py:TimingLM` -- `fill()` (139-147) and `make()` (152-160) duplicate
  timing wrap logic; extract a `_timed()` helper
- `work/models.py:17` -- `RoadmapData.phases` is `list[dict]`, should be typed
- `work/models.py:13` -- `ProjectState.status` is bare `str`, could be Enum
- `work/deps.py:68` -- `scan_secrets()` is a stub returning hardcoded `clean=True`
- `work/deps.py:106` -- `detect_brownfield()` is a stub returning empty result
- `repl/exec.py:14-25` -- `_ensure_cortex_module()` modifies `sys.modules` globally;
  not thread-safe (acceptable for single-process REPL)

## Per-file detail

### Clean files (no action needed)

| File | Lines | Notes |
|------|-------|-------|
| `bae/__init__.py` | 37 | Clean exports |
| `bae/markers.py` | 75 | Minimal, correct |
| `bae/exceptions.py` | 78 | Good inheritance, cause chaining |
| `bae/result.py` | 32 | Clean generic |
| `bae/agent.py` | 27 | Single function, correct |
| `bae/work/__init__.py` | 16 | Clean exports |
| `bae/work/execute_phase.py` | 99 | Clean node graph, good topology |
| `bae/work/plan_phase.py` | 106 | Clean node graph |
| `bae/work/quick.py` | 65 | Simple linear graph |
| `bae/work/new_project.py` | 276 | Complex but well-structured; custom __call__ justified |
| `bae/work/map_codebase.py` | 135 | map_one() closure creating Graph+LM is the intended dep pattern |
| `bae/repl/__init__.py` | 17 | Clean |
| `bae/repl/bash.py` | 47 | Clean, correct error handling |
| `bae/repl/channels.py` | 218 | Well-structured Protocol + dataclass |
| `bae/repl/complete.py` | 29 | Minimal rlcompleter wrapper |
| `bae/repl/modes.py` | 32 | Clean enum + dicts |
| `bae/repl/namespace.py` | 177 | Clean introspection, well-factored methods |
| `bae/repl/store.py` | 163 | Clean SQLite, FTS5, proper schema |
| `bae/repl/tasks.py` | 102 | Clean TaskManager, correct process group handling |
| `bae/repl/toolbar.py` | 162 | Well-structured; bare `except Exception:` on line 61 is intentional (widget render must not crash toolbar) |

### Files with findings

#### bae/graph.py (578 lines)
- Lines 25-43: `_get_base_type()` duplicates lm.py:121-125 (with extra union handling)
- Lines 46-52: `_build_context()` trivial, called once (line 431), inline it
- Lines 55-57: `_build_instruction()` returns class name, called twice (408, 441), inline it
- Lines 350: bare `except Exception as e:` after RecallError catch, converts to DepError
- Lines 487-577: `graph()` wrapper is 90 lines; complex but justified (signature introspection)

#### bae/node.py (220 lines)
- Line 194: `__call__` accepts `*_args, **_kwargs` never used

#### bae/lm.py (529 lines)
- Lines 33-110: `transform_schema()` is 77 lines -- could split by schema type
- Lines 121-125: `_get_base_type()` duplicated in graph.py:25-43

#### bae/resolver.py (524 lines)
- Lines 141-200 vs 326-368: `build_dep_dag()` and `_build_fn_dag()` near-identical walk
- Lines 273-323: `_resolve_one()` is 51 lines doing two jobs (Node-as-Dep vs callable)

#### bae/cli.py (275 lines)
- Line 242: duplicate `import json` (already at line 13)

#### bae/work/prompt.py (121 lines)
- Lines 79-111: 7 gate functions differ only in prompt string
- Lines 114-120: 7 Annotated gate aliases -- generate from dict

#### bae/work/deps.py (165 lines)
- Lines 68-71: `scan_secrets()` stub
- Lines 106-109: `detect_brownfield()` stub

#### bae/work/models.py (78 lines)
- Line 13: `ProjectState.status` is bare `str`
- Line 17: `RoadmapData.phases` is `list[dict]`

#### bae/repl/shell.py (522 lines)
- Lines 52-93: `_contains_coroutines()` and `_count_and_close_coroutines()` duplicate walk
- Lines 113-215: `_build_key_bindings()` is 102 lines of nested closures
- Lines 392-469: `_dispatch()` is 78 lines mixing PY/NL/BASH

#### bae/repl/engine.py (458 lines)
- Lines 132-164: `TimingLM.fill()` and `.make()` duplicate timing logic
- Lines 214-288 vs 313-382: `_execute()` and `_wrap_coro()` duplicate lifecycle boilerplate

#### bae/repl/views.py (312 lines)
- Lines 182-223: `_render_grouped_panel()` and `_render_code_panel()` share structure
  (title, Syntax, Rule, Panel construction) -- could extract shared panel builder

#### bae/repl/ai.py (548 lines)
- Lines 32-61: regex patterns are NOT duplicated from views.py -- they serve different
  purposes (ai.py detects/executes tool calls; views.py strips tags for display)

#### bae/repl/exec.py (69 lines)
- Lines 14-25: `_ensure_cortex_module()` modifies `sys.modules` globally; acceptable
  for single-process REPL but worth noting

## Corrections from original audit

1. **WRONG: `_unwrap_annotated()` duplicated in graph.py** -- graph.py:18 imports it from node.py
2. **WRONG: `_extract_types_from_hint()` reimplemented in graph.py** -- different functions
3. **WRONG: Strip regexes duplicated between ai.py and views.py** -- ai.py has tool-detection
   regexes (`_EXEC_BLOCK_RE`, `_TOOL_TAG_RE`, `_WRITE_TAG_RE`, `_EDIT_REPLACE_RE`, `_OSC8_TOOL_RE`);
   views.py has display-stripping regexes (`_STRIP_RUN_RE`, `_STRIP_TOOL_RE`, `_STRIP_WRITE_RE`).
   Different patterns for different purposes.
4. **WRONG: `build_dep_dag()` duplicates DAG walk in `resolve_fields()`** -- `resolve_fields()`
   calls `build_dep_dag()`, it doesn't reimplement it. The actual duplication is
   `build_dep_dag()` vs `_build_fn_dag()` (both build TopologicalSorters with identical walk).
5. **WRONG: `repl/graph_commands.py` references** -- this file does not exist
6. **WRONG: `_encode_mermaid_for_live()` duplicated between graph_show/graph_export** --
   graph_export uses mmdc subprocess, not mermaid encoding at all
7. **WRONG: File count "34"** -- there are 33 .py files under bae/
