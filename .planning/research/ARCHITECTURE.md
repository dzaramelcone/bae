# Architecture: Eval/Optimization DX Integration

**Domain:** Eval/optimization developer workflow for bae agent graphs
**Researched:** 2026-02-08
**Confidence:** HIGH (based on direct codebase analysis + DSPy official docs)

## Executive Summary

Bae has the optimization primitives (compiler.py, optimizer.py) and the graph introspection (Graph.nodes, Graph.edges, Graph.to_mermaid) but lacks the DX layer that connects them into a developer workflow. The architecture needs four new subsystems: (1) domain package discovery, (2) eval runner bridging Graph.run() to DSPy Evaluate, (3) dataset management, and (4) CLI commands orchestrating the pipeline.

The key architectural insight is that **Graph already knows everything** -- nodes, edges, field types, routing strategy. The eval/optimization DX is a projection of Graph's introspection, not a parallel system. Every new module should take a Graph as input and derive its behavior from Graph's existing topology discovery.

## Existing Architecture (What We Have)

### Component Map

```
bae/
  node.py        -- Node base class, _wants_lm, _has_ellipsis_body
  graph.py       -- Graph (discovery, run, validate, to_mermaid)
  markers.py     -- Dep(fn), Recall()
  resolver.py    -- classify_fields, resolve_fields, build_dep_dag
  compiler.py    -- node_to_signature, compile_graph, CompiledGraph, create_optimized_lm
  optimizer.py   -- trace_to_examples, node_transition_metric, optimize_node, save/load_optimized
  lm.py          -- LM Protocol, PydanticAIBackend, ClaudeCLIBackend
  dspy_backend.py -- DSPyBackend
  optimized_lm.py -- OptimizedLM extends DSPyBackend
  result.py      -- GraphResult[T]
  exceptions.py  -- BaeError hierarchy
  cli.py         -- Typer app with graph show/export/mermaid + run commands
  __init__.py    -- Public API
```

### Existing Integration Points

| Component | What It Provides to Eval/DX | How |
|-----------|---------------------------|-----|
| `Graph.nodes` | Set of all node types | Introspection target for eval scaffolding |
| `Graph.edges` | Adjacency list | Topology for diagrams and dependency ordering |
| `Graph.run()` | Execution with trace | Trace is the raw material for eval datasets |
| `Graph.to_mermaid()` | Diagram generation | Already exists, needs auto-write to package |
| `GraphResult.trace` | Ordered list[Node] | Input to trace_to_examples() |
| `compiler.compile_graph()` | CompiledGraph | Bridge to DSPy optimization |
| `compiler.create_optimized_lm()` | OptimizedLM | Production loading of compiled artifacts |
| `optimizer.trace_to_examples()` | list[dspy.Example] | Bridge from bae traces to DSPy eval format |
| `optimizer.save/load_optimized()` | Disk persistence | Compiled predictor JSON files |
| `cli._load_graph_from_module()` | Graph from module path | Reusable for all CLI commands |
| `cli.app` (Typer) | Existing graph subcommand | Extension point for eval/optimize commands |

### Existing Data Flow

```
Graph(start=Node) --> .run(input, lm) --> GraphResult
                                              |
                                              v
                                         .trace: list[Node]
                                              |
                                              v
                                    trace_to_examples(trace)
                                              |
                                              v
                                    list[dspy.Example]
                                              |
                                              v
                                    optimize_node(cls, trainset, metric)
                                              |
                                              v
                                    dspy.Predict (optimized)
                                              |
                                              v
                                    save_optimized() --> NodeName.json
                                              |
                                              v
                                    load_optimized() --> OptimizedLM
                                              |
                                              v
                                    graph.run(input, lm=OptimizedLM)
```

**The gap:** Nothing orchestrates this pipeline. The developer must manually call each step, manage file paths, and wire things together.

## Proposed Architecture (What We Need)

### New Modules

| Module | Purpose | Depends On |
|--------|---------|------------|
| `bae/package.py` | Domain package discovery + scaffolding | graph.py (for introspection) |
| `bae/eval.py` | Eval runner + metric defaults | graph.py, result.py |
| `bae/dataset.py` | Dataset loading/saving/management | result.py (for trace types) |
| `bae/cli.py` (extend) | New subcommands: eval, optimize, init, inspect | All of the above |

### Modified Modules

| Module | Change | Why |
|--------|--------|-----|
| `bae/graph.py` | No changes needed | Graph.run() already returns traces |
| `bae/compiler.py` | No changes needed | compile_graph() already works |
| `bae/optimizer.py` | Minor: accept custom optimizer type | Currently hardcodes BootstrapFewShot |
| `bae/cli.py` | Add eval, optimize, init, inspect subcommands | DX entry points |
| `bae/__init__.py` | Export new public API | Package completeness |

### Component Architecture

```
                    CLI Layer (bae/cli.py)
                    ________________________
                   |                        |
                   |  bae init <name>       |
                   |  bae run <pkg>         |  <-- already exists
                   |  bae eval <pkg>        |
                   |  bae optimize <pkg>    |
                   |  bae inspect <pkg>     |
                   |  bae graph show <pkg>  |  <-- already exists
                   |________________________|
                          |
                          v
                   Package Layer (bae/package.py)
                   ________________________________
                  |                                |
                  |  discover_package(path)         |
                  |  --> BaePackage(graph, datasets, |
                  |      compiled_dir, config)      |
                  |________________________________|
                          |
             ____________|_____________
            |            |             |
            v            v             v
     Eval Layer    Dataset Layer    Existing Layers
     (bae/eval.py) (bae/dataset.py) (graph, compiler, optimizer)
     ___________   ______________   ________________________
    |           | |              | |                        |
    | evaluate  | | load_dataset | | Graph.run()            |
    | EvalResult| | save_traces  | | compile_graph()        |
    | metrics   | | EvalDataset  | | optimize_node()        |
    |___________| |______________| | save/load_optimized()  |
                                   |________________________|
```

## Domain Package Structure

The "domain package" is the organizational unit that ties a graph definition to its eval data, compiled artifacts, and documentation. It is a standard Python package directory.

### Proposed Layout

```
my_domain/
  __init__.py          # exports `graph` (Graph instance)
  graph.py             # Node definitions + Graph(start=...) instantiation
  graph.md             # Auto-generated: mermaid diagram + node field docs
  eval.py              # Optional: custom metrics, eval config
  datasets/
    seed.jsonl         # Seed examples (input for start node)
    golden.jsonl       # Golden traces (input + expected output pairs)
  compiled/
    NodeA.json         # Optimized predictor for NodeA (DSPy format)
    NodeB.json         # Optimized predictor for NodeB
    .gitignore         # "*.json" -- compiled artifacts are regenerable
```

### Why This Structure

1. **graph.py is the anchor.** The Graph instance at module scope is the entry point for all operations. Already supported by `cli._load_graph_from_module()`.

2. **graph.md is auto-generated.** `bae init` or `bae graph update` writes it. Contains mermaid diagram and a field-level reference. Developers can add notes but the structured sections are regenerated.

3. **eval.py is optional.** Zero-config eval uses default metrics. Custom metrics live here when needed. Progressive complexity: you don't need this file until you outgrow defaults.

4. **datasets/ is flat JSONL.** Each line is a JSON object. Seed files have only start-node fields. Golden files have full traces. JSONL because it's append-friendly and git-diffable.

5. **compiled/ is .gitignore-able.** Compiled artifacts are derived from graph + datasets + optimization runs. They can be regenerated. Some teams may want to commit them for reproducibility; .gitignore is a suggestion, not enforced.

### Package Discovery

`bae/package.py` discovers a domain package from a path:

```python
@dataclass
class BaePackage:
    """Discovered domain package with all its components."""
    name: str                      # Package name (directory name)
    path: Path                     # Absolute path to package directory
    graph: Graph                   # Loaded Graph instance
    graph_module: str              # Importable module path (e.g. "my_domain.graph")
    dataset_dir: Path              # path / "datasets"
    compiled_dir: Path             # path / "compiled"
    eval_module: ModuleType | None # Loaded eval.py if exists
```

Discovery algorithm:
1. Given a path, check if it's a Python package (has `__init__.py`)
2. Import `{package_name}.graph` and find `graph` attribute (Graph instance)
3. Check for optional `eval.py`, `datasets/`, `compiled/`
4. Return BaePackage with everything populated

This reuses and extends the existing `_load_graph_from_module()` pattern from cli.py.

## Eval Runner Design

### Core Question: Wrap or Extend Graph.run()?

**Answer: Wrap.** The eval runner calls Graph.run() inside a loop, collects traces, and scores them. It does not modify Graph.run()'s behavior.

Rationale:
- Graph.run() is the execution primitive. It should not know about eval.
- Eval is a higher-level concern: "run this graph N times with different inputs, score each run."
- DSPy's Evaluate class follows the same pattern -- it wraps a Module's __call__.

### Architecture

```python
@dataclass
class EvalResult:
    """Result of evaluating a graph on a dataset."""
    score: float                           # Aggregate score (0-100)
    results: list[tuple[dict, GraphResult, float]]  # (input, result, score)
    metadata: dict                         # Timing, error counts, etc.


def evaluate(
    graph: Graph,
    dataset: list[dict],                   # List of start-node field dicts
    metric: Callable[[GraphResult], float] | None = None,
    lm: LM | None = None,
    max_iters: int = 10,
) -> EvalResult:
    """Run graph on each dataset example and score with metric.

    Default metric: terminal node is not None (graph completes successfully).
    """
```

### Metric Protocol

Metrics are plain functions. No base class, no registration -- just a callable.

```python
# Simplest metric: did the graph complete?
def completion_metric(result: GraphResult) -> float:
    return 1.0 if result.trace else 0.0

# Field-level metric: does the terminal node have non-empty fields?
def field_completeness_metric(result: GraphResult) -> float:
    terminal = result.result
    if terminal is None:
        return 0.0
    fields = terminal.model_dump()
    filled = sum(1 for v in fields.values() if v)
    return filled / len(fields) if fields else 0.0

# LLM-as-judge metric: use DSPy Assess pattern
def quality_metric(result: GraphResult) -> float:
    # Uses dspy.Predict with an Assess signature
    ...
```

Progressive complexity tiers for metrics:
1. **Zero-config:** Graph completes without error -> 1.0
2. **Field-level:** Terminal node fields are non-empty, well-formed
3. **Golden trace:** Compare output to expected output (from golden.jsonl)
4. **Custom function:** User writes arbitrary scoring logic in eval.py
5. **LLM-as-judge:** DSPy Assess pattern with instruction-tuned judge

### Connection to DSPy's Evaluate

Bae's `evaluate()` is intentionally **not** a wrapper around `dspy.Evaluate`. The reasons:

1. `dspy.Evaluate` expects a `dspy.Module` -- bae's Graph is not a dspy.Module.
2. `dspy.Evaluate` uses `dspy.Example` -- bae uses plain dicts for inputs and GraphResult for outputs.
3. The metric signature differs: DSPy expects (example, pred, trace), bae's natural metric signature is (result: GraphResult) -> float.

However, **when optimizing**, we bridge to DSPy's format:
- `trace_to_examples()` already converts bae traces to `dspy.Example` format
- `CompiledGraph.optimize()` already uses `dspy.teleprompt.BootstrapFewShot`
- The bridge is at the optimizer boundary, not the eval boundary

This keeps bae's eval API clean and Python-native while still leveraging DSPy's optimization machinery.

## Dataset Management

### Format: JSONL

Each line is a JSON object. Two dataset types:

**Seed dataset (inputs only):**
```jsonl
{"user_message": "ugh i just got up"}
{"user_message": "heading to a wedding this afternoon"}
{"user_message": "job interview tomorrow, need to look sharp"}
```

**Golden dataset (inputs + expected terminal output):**
```jsonl
{"input": {"user_message": "ugh i just got up"}, "expected": {"top": "oversized sweater", "bottom": "joggers"}}
```

### Dataset API

```python
@dataclass
class EvalDataset:
    """A named collection of eval examples."""
    name: str
    path: Path
    examples: list[dict]

    @classmethod
    def load(cls, path: Path) -> EvalDataset: ...

    @classmethod
    def from_traces(cls, traces: list[list[Node]], name: str) -> EvalDataset:
        """Convert collected execution traces to a dataset."""
        ...

    def save(self, path: Path | None = None) -> None: ...
```

### Trace Collection for Dataset Building

A natural workflow: run the graph a few times, collect traces, save as golden dataset.

```
bae run my_domain -i '{"user_message": "..."}' --save-trace
# Appends trace to my_domain/datasets/traces.jsonl

bae eval my_domain
# Uses seed.jsonl for inputs, scores with default metric
```

## Compiled Artifact Flow

### Current (What Exists)

`optimizer.save_optimized()` writes `{NodeClassName}.json` to a directory.
`optimizer.load_optimized()` reads them back.
`compiler.create_optimized_lm()` creates an OptimizedLM from a directory.

### Proposed (What Changes)

The compiled directory lives inside the domain package: `my_domain/compiled/`.

No changes to save/load format. The only change is making the CLI commands know where to read/write:

```
bae optimize my_domain
# Runs optimization, writes to my_domain/compiled/
# Equivalent to:
#   compiled = compile_graph(graph)
#   compiled.optimize(trainset)
#   compiled.save("my_domain/compiled/")

bae run my_domain --optimized
# Loads from my_domain/compiled/ and runs with OptimizedLM
# Equivalent to:
#   lm = create_optimized_lm(graph, "my_domain/compiled/")
#   graph.run(start_node, lm=lm)
```

### Runtime Loading

For production use (not via CLI):

```python
from my_domain.graph import graph
from bae import create_optimized_lm

lm = create_optimized_lm(graph, "my_domain/compiled/")
result = graph.run(StartNode(user_message="..."), lm=lm)
```

This already works with existing `create_optimized_lm()`. No new API needed -- just DX to make the path conventional.

## CLI Architecture

### Current Commands

```
bae
  graph
    show <module>       # Open mermaid.live in browser
    export <module>     # Export to SVG/PNG via mmdc
    mermaid <module>    # Print mermaid to stdout
  run <module>          # Run graph with optional input
```

### Proposed Commands

```
bae
  init <name>           # Scaffold a domain package
  run <pkg>             # Run graph (existing, enhance with --save-trace, --optimized)
  eval <pkg>            # Evaluate graph on dataset
  optimize <pkg>        # Optimize graph with DSPy
  inspect <pkg>         # Show graph info (nodes, fields, metrics, compiled status)
  graph
    show <module>       # Open mermaid.live (existing)
    export <module>     # Export to file (existing)
    mermaid <module>    # Print mermaid (existing)
    update <pkg>        # Regenerate graph.md
```

### CLI Module Organization

The existing `cli.py` is 283 lines. Adding all new commands in one file is fine as long as the CLI stays thin -- argument parsing and delegation to service modules (eval.py, package.py, dataset.py).

**Recommendation:** Keep a single `cli.py` file. The commands are thin wrappers. Factor complex logic into eval.py, package.py, dataset.py. Only split if cli.py exceeds ~500 lines.

### Command Detail: `bae init`

```
bae init my_domain
```

Creates:
```
my_domain/
  __init__.py           # from .graph import graph
  graph.py              # Skeleton with example nodes
  graph.md              # Auto-generated from skeleton
  datasets/
    seed.jsonl           # Empty or single-example
  compiled/
    .gitignore           # *.json
```

### Command Detail: `bae eval`

```
bae eval my_domain                    # Default metric, seed dataset
bae eval my_domain -d golden.jsonl    # Specific dataset
bae eval my_domain -m quality         # Named metric from eval.py
bae eval my_domain --save results.json  # Save detailed results
```

Flow:
1. Discover package via `discover_package()`
2. Load dataset (default: `datasets/seed.jsonl`)
3. Load metric (default: completion, or from eval.py)
4. Call `evaluate(graph, dataset, metric)`
5. Display EvalResult (score, per-example breakdown)

### Command Detail: `bae optimize`

```
bae optimize my_domain                     # BootstrapFewShot (default)
bae optimize my_domain --optimizer mipro   # MIPROv2
bae optimize my_domain --eval-after        # Run eval after optimization
```

Flow:
1. Discover package
2. Load training dataset (default: `datasets/golden.jsonl`)
3. Compile graph: `compile_graph(graph)`
4. Optimize: `compiled.optimize(trainset, metric)`
5. Save: `compiled.save("my_domain/compiled/")`
6. Optionally run eval on optimized graph

### Command Detail: `bae inspect`

```
bae inspect my_domain
```

Output:
```
Package: my_domain
Graph: 3 nodes, 2 edges
  IsTheUserGettingDressed --> AnticipateUsersDay
  AnticipateUsersDay --> RecommendOOTD
  RecommendOOTD --> (terminal)

Datasets:
  seed.jsonl: 10 examples
  golden.jsonl: 25 examples

Compiled:
  AnticipateUsersDay.json: 4 demos
  RecommendOOTD.json: 8 demos
  IsTheUserGettingDressed.json: (missing)

Eval:
  Last score: 72.3% (2026-02-08)
```

## Progressive Complexity Tiers

The tiers are **not** architecturally separate modules. They are **levels of configuration** within the same modules.

### Tier 0: Zero Config

```
bae init my_domain
# Edit graph.py with your nodes
bae eval my_domain
```

Uses:
- Default completion metric
- Auto-generated seed dataset from start node defaults (if possible)
- No optimization

### Tier 1: Custom Data

```
# Add examples to datasets/seed.jsonl
bae eval my_domain
```

Uses:
- Default completion metric
- User-provided seed data
- No optimization

### Tier 2: Custom Metrics

```python
# my_domain/eval.py
def metric(result):
    """Custom quality metric."""
    terminal = result.result
    return 1.0 if terminal and len(terminal.final_response) > 50 else 0.0
```

```
bae eval my_domain
# Auto-discovers metric from eval.py
```

### Tier 3: Optimization

```
bae optimize my_domain
bae eval my_domain --optimized
bae run my_domain --optimized -i '{"user_message": "..."}'
```

### Tier 4: Advanced (MIPROv2, Custom Optimizers)

```python
# my_domain/eval.py
from bae.eval import EvalConfig

config = EvalConfig(
    optimizer="mipro",
    max_bootstrapped_demos=8,
    num_trials=50,
)
```

The architecture supports this by:
- `eval.py` is an optional configuration surface
- Config discovery is convention-based (look for `config` attribute in eval.py)
- Defaults are sensible at every tier
- No tier requires understanding the tier above it

## Data Flow: Complete Pipeline

```
                    [Developer writes graph.py]
                              |
                              v
                    bae init my_domain
                    bae graph update my_domain
                              |
                              v
                    [Developer adds seed data]
                    my_domain/datasets/seed.jsonl
                              |
                              v
                    bae eval my_domain
                              |
                    __________|__________
                   |                     |
                   v                     v
            evaluate()            Display EvalResult
            for each input:       (score, per-example)
              Graph.run(input)
              metric(result)
                   |
                   v
            [Developer reviews, adds golden traces]
            my_domain/datasets/golden.jsonl
                              |
                              v
                    bae optimize my_domain
                              |
                    __________|__________
                   |          |          |
                   v          v          v
            compile_graph  trace_to_examples  optimize_node
                   |          |               (BootstrapFewShot)
                   v          v                    |
            CompiledGraph  dspy.Example list       v
                   |_________________________ dspy.Predict
                                              (optimized)
                              |
                              v
                    save_optimized()
                    my_domain/compiled/NodeA.json
                              |
                              v
                    bae run my_domain --optimized
                              |
                              v
                    create_optimized_lm(graph, "my_domain/compiled/")
                              |
                              v
                    graph.run(input, lm=OptimizedLM)
```

## Suggested Build Order

Based on dependency analysis, the build order should be:

### Phase 1: Package Foundation

**New:** `bae/package.py` + `bae init` CLI command + `bae graph update` command

Why first: Everything else needs package discovery. The domain package structure is the organizational primitive. Without it, eval and optimize don't know where to find data or write artifacts.

Dependencies: Only `bae/graph.py` (for Graph import) and `bae/cli.py` (for command registration).

Deliverables:
- `BaePackage` dataclass
- `discover_package()` function
- `bae init <name>` command (scaffold domain package)
- `bae graph update <pkg>` command (auto-generate graph.md with mermaid + field docs)
- `bae inspect <pkg>` command (show package status)

### Phase 2: Dataset + Eval

**New:** `bae/dataset.py` + `bae/eval.py` + `bae eval` CLI command

Why second: Eval is the feedback loop. You need to measure before you can optimize. This is the highest-value feature for developers.

Dependencies: Phase 1 (package discovery), `bae/graph.py` (Graph.run), `bae/result.py` (GraphResult).

Deliverables:
- `EvalDataset` class with load/save from JSONL
- `evaluate()` function wrapping Graph.run() in a scoring loop
- `EvalResult` dataclass with aggregate score + per-example breakdown
- Default metrics (completion, field completeness)
- `bae eval <pkg>` command
- `bae run <pkg> --save-trace` enhancement for dataset building

### Phase 3: Optimize Integration

**Modified:** `bae/optimizer.py` (parameterize optimizer type) + `bae optimize` CLI command

Why third: Optimization depends on having eval data and metrics. The optimization primitives already exist -- this phase wires them into the CLI and package workflow.

Dependencies: Phase 2 (datasets, metrics), `bae/compiler.py`, `bae/optimizer.py`.

Deliverables:
- `bae optimize <pkg>` command
- `bae run <pkg> --optimized` flag
- Configurable optimizer selection (BootstrapFewShot, MIPROv2)
- Post-optimization eval comparison

### Phase 4: Polish + Advanced

**Enhancements across all modules**

Why last: Polish after core workflow works end-to-end.

Deliverables:
- LLM-as-judge metric helpers
- Eval result persistence and comparison (`bae eval <pkg> --compare baseline.json`)
- Tier 4 config surface (EvalConfig in eval.py)
- Better error messages and progress display

## Anti-Patterns to Avoid

### Anti-Pattern: DSPy Module Wrapper

**Do not** make Graph a subclass of `dspy.Module`. Graph has its own execution model (step-by-step with resolve/fill). Wrapping it in dspy.Module would require adapting Graph.run() to DSPy's forward() convention, losing type safety and trace structure.

**Instead:** Bridge at the data boundary. Use `trace_to_examples()` to convert bae outputs to DSPy inputs. Keep Graph.run() as the execution primitive.

### Anti-Pattern: Eval Config as YAML/TOML

**Do not** introduce a new config file format (eval.yaml, bae.toml). Python files are more powerful and already the project's language.

**Instead:** Convention-based discovery in eval.py. A `metric` function, a `config` object -- all optional, all Python.

### Anti-Pattern: Abstract Metric Base Class

**Do not** create `class Metric(ABC)` with `score()` method. This adds ceremony for no benefit.

**Instead:** Metrics are plain callables: `Callable[[GraphResult], float]`. Any function works. Any lambda works. No registration, no subclassing.

### Anti-Pattern: Separate Compiled Registry

**Do not** build a global registry of compiled predictors. The filesystem (my_domain/compiled/) IS the registry.

**Instead:** `create_optimized_lm(graph, path)` already loads from disk. The convention is: compiled artifacts live in the package's `compiled/` directory.

### Anti-Pattern: graph.md as Required

**Do not** make graph.md a required file that blocks eval. It's a generated documentation artifact.

**Instead:** graph.md is auto-generated on `bae init` and `bae graph update`. Its absence doesn't block any operation.

## Integration Points Summary

| Existing Component | New Component | Integration Type | Details |
|---------------------|---------------|------------------|---------|
| `Graph` | `BaePackage` | Composition | BaePackage holds a Graph |
| `Graph.run()` | `evaluate()` | Call | evaluate() calls Graph.run() in a loop |
| `Graph.start` | `bae init` | Read | Scaffold uses start node's fields for seed data template |
| `GraphResult.trace` | `EvalDataset.from_traces()` | Conversion | Traces become dataset examples |
| `trace_to_examples()` | `bae optimize` | Call | CLI uses existing function |
| `compile_graph()` | `bae optimize` | Call | CLI uses existing function |
| `save_optimized()` | `bae optimize` | Call | Writes to pkg.compiled_dir |
| `create_optimized_lm()` | `bae run --optimized` | Call | Loads from pkg.compiled_dir |
| `cli._load_graph_from_module()` | `discover_package()` | Subsumes | Package discovery is superset of module loading |
| `cli.app` (Typer) | New commands | Extension | `@app.command()` additions |
| `Graph.to_mermaid()` | `bae graph update` | Call | Writes mermaid to graph.md |
| `Graph.nodes` / `Graph.edges` | `bae inspect` | Read | Display graph topology |
| `classify_fields()` | graph.md generation | Call | Document field types per node |
| `_get_routing_strategy()` | `bae inspect` | Call | Show routing info per node |

## Open Design Questions

### 1. Metric signature: (GraphResult) or (example, result)?

The current proposal uses `Callable[[GraphResult], float]`. But golden-trace metrics need access to the expected output too. Two options:

**Option A:** `Callable[[GraphResult], float]` -- metric only sees the result. Golden comparison happens outside the metric (dataset loader attaches expected to result metadata).

**Option B:** `Callable[[dict, GraphResult], float]` -- metric sees both input and result. Cleaner for golden trace comparison.

**Recommendation:** Option B. The input dict is cheap to pass and enables golden-trace metrics without monkey-patching GraphResult.

### 2. Dataset file naming convention

Should seed vs golden be distinguished by filename convention or by content structure?

**Recommendation:** Filename convention. `seed.jsonl` has input dicts, `golden.jsonl` has `{"input": ..., "expected": ...}` dicts. The loader infers format from filename prefix or structure detection.

### 3. graph.md format

How much documentation goes in graph.md? Options:

**Minimal:** Just mermaid diagram + node list
**Medium:** Mermaid + field table per node (type, annotation, description)
**Full:** Mermaid + fields + routing strategy + dep chain visualization

**Recommendation:** Medium. Field tables are useful for developers; routing strategy and dep chains are available via `bae inspect` and don't need to be in a static file.

## Sources

- [DSPy Evaluate API](https://dspy.ai/api/evaluation/Evaluate/) - HIGH confidence
- [DSPy Evaluation Overview](https://dspy.ai/learn/evaluation/overview/) - HIGH confidence
- [DSPy Metrics](https://dspy.ai/learn/evaluation/metrics/) - HIGH confidence
- [DSPy Optimizers](https://dspy.ai/learn/optimization/optimizers/) - HIGH confidence
- [DSPy Cheatsheet](https://dspy.ai/cheatsheet/) - HIGH confidence
- [Typer Subcommands](https://typer.tiangolo.com/tutorial/subcommands/add-typer/) - HIGH confidence
- Direct codebase analysis of all bae/ source files - HIGH confidence

---
*Architecture research: 2026-02-08 -- eval/optimization DX integration*
