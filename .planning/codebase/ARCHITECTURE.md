# Architecture

**Analysis Date:** 2026-02-14

## Pattern Overview

**Overall:** Type-driven agent graphs with dependency injection

**Key Characteristics:**
- Graph topology discovered from Python type hints on Node.__call__ return types
- Execution state flows through immutable Node instances (Pydantic models)
- Dependency injection via Annotated[T, Dep()] and Annotated[T, Recall()] markers
- LM backend produces typed Node instances via constrained decoding (JSON schemas)
- Async-first execution with topological sorting for parallel dependency resolution

## Layers

**Node Layer:**
- Purpose: State containers and routing logic
- Location: `bae/node.py`
- Contains: Node base class (Pydantic BaseModel), ellipsis detection, successor extraction
- Depends on: `bae/lm.py` (LM protocol for type hints)
- Used by: User-defined node classes, `bae/graph.py` execution loop

**Graph Layer:**
- Purpose: Topology discovery and execution orchestration
- Location: `bae/graph.py`
- Contains: Graph class, discovery via BFS over type hints, async execution loop
- Depends on: `bae/node.py`, `bae/resolver.py`, `bae/lm.py`, `bae/result.py`
- Used by: CLI commands (`bae/cli.py`), user applications

**Resolver Layer:**
- Purpose: Dependency injection and trace recall
- Location: `bae/resolver.py`
- Contains: Field classification, topological sorting, concurrent dep resolution
- Depends on: `bae/markers.py`, `bae/exceptions.py`
- Used by: `bae/graph.py` execution loop (resolves fields before each node)

**LM Layer:**
- Purpose: Language model abstraction for typed output
- Location: `bae/lm.py`
- Contains: LM protocol, ClaudeCLIBackend, JSON schema transformations, fill/choose_type API
- Depends on: `bae/resolver.py` (classify_fields)
- Used by: `bae/graph.py` execution loop, `bae/node.py` default __call__

**CLI Layer:**
- Purpose: Command-line interface and graph visualization
- Location: `bae/cli.py`
- Contains: Typer app, graph show/export/run commands, mermaid encoding
- Depends on: `bae/graph.py`, `bae/lm.py`
- Used by: End users via `bae` command

**REPL Layer:**
- Purpose: Interactive development environment with AI assistance
- Location: `bae/repl/`
- Contains: CortexShell (prompt_toolkit REPL), AI assistant, mode switching, task management
- Depends on: Core bae types (Node, Graph, LM)
- Used by: CLI entrypoint (`bae` with no args)

## Data Flow

**Graph Execution Flow:**

1. User creates start node instance with initial state
2. Graph.run/arun() begins execution loop with empty trace
3. For each node:
   - resolve_fields() resolves Dep/Recall annotations via topological sort
   - Resolved values set on node instance via object.__setattr__
   - Node appended to trace
   - Routing strategy determined (_get_routing_strategy):
     - Terminal: exit loop
     - Custom __call__: invoke directly (LM injected if _wants_lm)
     - Ellipsis body: LM routing via choose_type/fill
4. Loop terminates when current = None
5. Return GraphResult with trace

**Dependency Resolution Flow:**

1. classify_fields() categorizes each field as dep/recall/plain
2. build_dep_dag() constructs topological sorter from Dep annotations
3. dag.prepare() orders deps by level
4. For each level, asyncio.gather() resolves deps in parallel
5. Results cached in dep_cache (keyed by callable identity)
6. recall_from_trace() searches backwards through trace for type matches
7. Return dict of resolved field values

**LM Fill Flow:**

1. Graph calls lm.fill(target_type, resolved, instruction, source)
2. _build_plain_model() creates dynamic Pydantic model with only plain fields
3. _build_fill_prompt() serializes source node + resolved context to JSON
4. ClaudeCLIBackend calls `claude` subprocess with --json-schema
5. Structured output parsed from CLI JSON stream
6. validate_plain_fields() validates LLM output through plain model
7. Merge resolved + validated fields via model_construct()
8. Return fully populated target node instance

**State Management:**
- Graph execution is stateless (pure function from start node → GraphResult)
- Per-run state in dep_cache dict (shared across resolve_fields calls)
- Trace is append-only list of Node instances

## Key Abstractions

**Node:**
- Purpose: State container with routing logic
- Examples: `bae/node.py`, user-defined nodes in `examples/ootd.py`
- Pattern: Pydantic BaseModel subclass with async __call__ returning Node | None

**Dep/Recall Markers:**
- Purpose: Declarative dependency injection via type annotations
- Examples: `Annotated[str, Dep(get_data)]`, `Annotated[Analysis, Recall()]`
- Pattern: Dataclass markers in Annotated metadata, consumed by resolver

**Graph:**
- Purpose: Topology container and execution engine
- Examples: `Graph(start=AnalyzeRequest)` in user code
- Pattern: Discover via BFS, execute via async loop with field resolution

**LM Protocol:**
- Purpose: Backend-agnostic typed output interface
- Examples: `ClaudeCLIBackend`, future OpenAI/Anthropic API backends
- Pattern: Protocol with fill/choose_type methods, constrained decoding via JSON schemas

**GraphResult:**
- Purpose: Execution outcome with trace
- Examples: `result.trace`, `result.result` (terminal node)
- Pattern: Dataclass with Generic[T] for type-safe terminal access

## Entry Points

**CLI Entry:**
- Location: `bae/cli.py:main()`
- Triggers: `bae` command
- Responsibilities: Parse args, dispatch to subcommand or launch REPL

**REPL Entry:**
- Location: `bae/repl/__init__.py:launch()`
- Triggers: `bae` with no args
- Responsibilities: Start async CortexShell REPL

**Graph Execution Entry:**
- Location: `bae/graph.py:Graph.run()` or `Graph.arun()`
- Triggers: User code calls graph.run(start_node, lm=lm)
- Responsibilities: Execute graph from start node, return GraphResult

**Module Import:**
- Location: `bae/__init__.py`
- Triggers: `from bae import Node, Graph, LM, Dep, Recall`
- Responsibilities: Export public API

## Error Handling

**Strategy:** Exception hierarchy with cause chaining and trace attachment

**Patterns:**
- All exceptions inherit from BaeError with optional __cause__
- DepError: Raised when Dep function fails, attaches node_type and trace
- RecallError: Raised when Recall() finds no matching field in trace
- FillError: Raised when LM validation fails after retries, attaches attempts
- BaeLMError: Raised on LM API failures (timeout, network, invalid response)
- Trace attached to errors in graph.py execution loop via `err.trace = trace`

## Cross-Cutting Concerns

**Logging:** Python logging module, logger in `bae/graph.py` for field resolution debugging

**Validation:** Pydantic validation at LM boundary (validate_plain_fields), separate from dep/recall validation

**Authentication:** Not applicable (LM backend handles credentials via Claude CLI)

---

*Architecture analysis: 2026-02-14*
