---
status: investigating
trigger: "Investigate why `inspect g1` output is hard to read — fields not aligned with their nodes, no per-node timing shown, and the trace is a wall of text without indenting or formatting."
created: 2026-02-15T00:00:00Z
updated: 2026-02-15T00:00:00Z
---

## Current Focus

hypothesis: inspect command has three distinct formatting problems: (1) only terminal node shows fields, (2) no per-node timing in trace section, (3) fields dumped as raw repr
test: read _cmd_inspect implementation and trace what data is available
expecting: find where formatting logic is and confirm data availability
next_action: analyze evidence to determine root causes

## Symptoms

expected: Each node in trace should show its fields (formatted nicely), with per-node timing inline
actual: Only terminal node shows fields (as raw dict repr), no per-node timing in trace, all nodes in flat list
errors: none (cosmetic/UX issue)
reproduction: run any graph in GRAPH mode, then `inspect g1`
started: original implementation (phase 27)

## Eliminated

(none yet)

## Evidence

- timestamp: 2026-02-15T00:00:00Z
  checked: bae/repl/graph_commands.py _cmd_inspect (lines 156-197)
  found: |
    - Lines 178-182: Separate "Timings:" section exists, shows all node_timings
    - Lines 184-194: "Trace:" section iterates trace, but only shows terminal node fields
    - Line 189: `if i == len(trace):` — only the last (terminal) node gets fields shown
    - Line 192: Fields shown as `node.model_dump()` which produces raw dict repr
    - Line 194: Non-terminal nodes only show type name, no fields or timing
  implication: The code intentionally skips fields for non-terminal nodes. This is design decision, not bug.

- timestamp: 2026-02-15T00:00:00Z
  checked: bae/repl/engine.py NodeTiming and GraphRun structure
  found: |
    - NodeTiming has: node_type (str), start_ns, end_ns, duration_ms property
    - GraphRun.node_timings is list[NodeTiming]
    - TimingLM records timing for fill() and make() calls
    - submit_coro does NOT use TimingLM, so node_timings may be empty for coroutines
  implication: Timing data exists in run.node_timings but is shown in separate section, not inline with trace

- timestamp: 2026-02-15T00:00:00Z
  checked: GraphResult and trace structure
  found: |
    - GraphResult.trace is list[Node] instances
    - Each node instance has all its field values
    - node.model_dump() produces nested dicts (e.g., {'wardrobe': {'user_info': {...}}})
    - No timing data attached to individual nodes in trace
  implication: All field data is available, but formatting choice is to hide it for non-terminal nodes

- timestamp: 2026-02-15T00:00:00Z
  checked: How timing and trace relate
  found: |
    - run.node_timings: list[NodeTiming] with node_type as string
    - run.result.trace: list[Node] instances
    - No direct link between them (must match by type(node).__name__ == nt.node_type)
    - trace can have multiple nodes of same type (timing_map would only keep last)
  implication: Matching timing to trace node is non-trivial if same node type appears multiple times

## Resolution

root_cause: |
  Three separate design/implementation issues in _cmd_inspect:

  1. **Only terminal node shows fields** (line 189-192)
     - Intentional design: `if i == len(trace):` special-cases last node
     - Rationale unclear (maybe to reduce output clutter?)
     - Result: User can't see intermediate node field values

  2. **No per-node timing in trace section** (lines 184-194)
     - Timing shown in separate "Timings:" section (lines 178-182)
     - Trace section doesn't reference timing data at all
     - Result: Can't see which node took how long in trace flow

  3. **Fields formatted as raw repr** (line 192)
     - Uses `node.model_dump()` which produces plain dict
     - Directly interpolated into f-string: `f"  {i}. {type(node).__name__}  {fields}"`
     - Nested dicts become unreadable wall of text
     - Result: Large nested structures are illegible

  **Why this is hard to fix well:**
  - Same node type can appear multiple times in trace (can't use simple dict lookup)
  - Need to match timing data (by index or type) to trace nodes
  - Need rich formatting (indentation, syntax highlighting) for nested fields
  - Trade-off between verbosity and completeness

suggested_improvements: |
  **Option A: Inline timing, show all fields (verbose)**

  Replace separate Timings/Trace sections with single unified trace:

  ```
  Trace:
    1. IsTheUserGettingDressed (120ms)
       {
         "user_info": {
           "name": "Dzara",
           "age": 30
         }
       }

    2. AnticipateUsersDay (2300ms)
       {
         "user_info": {...},
         "schedule": [...]
       }
  ```

  Implementation:
  - Build timing_by_index: list matching trace indices to NodeTiming
  - For each node: show name, timing (if available), fields (JSON formatted with indent)
  - Use json.dumps(node.model_dump(), indent=2) for readable nested structures
  - Optionally wrap in Syntax(..., 'json', theme='monokai') for colors

  Pros: Complete information, timing aligned with nodes
  Cons: Verbose for graphs with many nodes or large field values

  **Option B: Inline timing, fields on demand (balanced)**

  Show all nodes with timing, but only show fields for:
  - Start node (what came in)
  - Terminal node (what came out)
  - Any node that user explicitly wants to see (future: `inspect g1 --node AnticipateUsersDay`)

  ```
  Trace:
    1. IsTheUserGettingDressed (120ms)
    2. AnticipateUsersDay (2300ms)
    3. RecommendOOTD (450ms)
       {
         "wardrobe": {...},
         "recommendation": "..."
       }
  ```

  Implementation:
  - Similar to Option A but conditional field display
  - Keep special case for terminal node, add start node

  Pros: Cleaner output, still shows flow and timing
  Cons: Can't see intermediate state without separate command

  **Option C: Hierarchical panel display (rich)**

  Use Rich Panel per node with collapsible-style formatting:

  ```
  ╭─ 1. IsTheUserGettingDressed (120ms) ─╮
  │ user_info: {name: "Dzara", age: 30}  │
  ╰──────────────────────────────────────╯

  ╭─ 2. AnticipateUsersDay (2300ms) ─────╮
  │ user_info: {...}                     │
  │ schedule: [3 items]                  │
  ╰──────────────────────────────────────╯
  ```

  Implementation:
  - For each node, create Rich Panel with node name + timing as title
  - Panel content: Syntax(json.dumps(node.model_dump(), indent=2), 'json')
  - Use _rich_to_ansi() to convert to ANSI for router.write()

  Pros: Beautiful, clear separation, syntax highlighting
  Cons: Most verbose, might be too much for large graphs

  **Recommendation: Start with Option B**

  - Provides immediate value (inline timing)
  - Reduces verbosity compared to current "all fields on terminal node"
  - Can evolve to Option A or C based on user feedback
  - Implementation is straightforward (minimal changes to existing code)

  **Technical notes:**

  1. Timing lookup challenge:
     - run.node_timings may not align 1:1 with trace if submit_coro was used
     - Multiple nodes of same type: can't use dict by node_type
     - Solution: Build timing_by_index during iteration, match by position

  2. Field formatting:
     - json.dumps(node.model_dump(), indent=2) is simplest
     - Rich Syntax adds colors: Syntax(json.dumps(...), 'json', theme='monokai')
     - Tree structure possible but harder to read for nested dicts

  3. Integration with existing code:
     - graph_commands.py already imports Text from rich
     - views.py has _rich_to_ansi() helper
     - Can use Text() for simple formatting or Panel() for complex
     - All output goes through router.write() with metadata={"type": "ansi"}

fix: (not requested - investigation only)
verification: (not requested - investigation only)
files_changed: []
