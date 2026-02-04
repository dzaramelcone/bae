# Architecture

**Analysis Date:** 2026-02-04

## Pattern Overview

**Overall:** Declarative Graph with Type-Driven Topology Discovery

**Key Characteristics:**
- Node state is declared via Pydantic BaseModel fields
- Graph topology is discovered from return type annotations on `__call__` methods
- LM (Language Model) is injected as a tool, not embedded in the framework
- Execution is synchronous and step-based with max-step protection
- Python 3.14+ required for PEP 649 deferred annotation evaluation

## Layers

**Node Layer:**
- Purpose: Represents individual states in the agent graph; contains domain state and routing logic
- Location: `bae/node.py`
- Contains: `Node` base class (extends Pydantic BaseModel), `NodeConfig` (per-node LLM configuration)
- Depends on: Pydantic 2.0+
- Used by: Graph, LM backends, user application code

**Graph Layer:**
- Purpose: Discovers topology from node type hints; manages execution loop and validation
- Location: `bae/graph.py`
- Contains: `Graph` class for topology discovery, execution, validation, and Mermaid visualization
- Depends on: Node layer
- Used by: Application entry points, LM backends

**LM Abstraction Layer:**
- Purpose: Clean protocol for language model backends to produce typed node instances
- Location: `bae/lm.py`
- Contains: `LM` protocol (defines interface), `PydanticAIBackend` (pydantic-ai), `ClaudeCLIBackend` (subprocess)
- Depends on: Node layer, pydantic-ai
- Used by: Graph execution loop, user nodes

**Compiler Layer (Not Wired):**
- Purpose: DSPy compilation for prompt optimization (placeholder)
- Location: `bae/compiler.py`
- Contains: `CompiledGraph`, `node_to_signature()`, `compile_graph()` stubs
- Depends on: Graph layer
- Used by: Not currently integrated

## Data Flow

**Node Execution Cycle:**

1. Graph starts with an initial node instance (state populated)
2. Graph calls `node(lm=lm_backend)` which invokes `Node.__call__(lm)`
3. Node's `__call__` method:
   - Examines its own state
   - Calls `lm.make(self, TargetType)` to produce a specific node type, OR
   - Calls `lm.decide(self)` to let LLM choose among successors
4. LM backend:
   - Converts current node state to prompt via `_node_to_prompt(node)`
   - Includes node docstring as context
   - Calls Claude (via pydantic-ai or CLI) with schema for target type(s)
   - Validates and returns typed instance
5. Graph receives next node instance and repeats (step 2) or returns if None

**State Management:**
- State flows forward: each node is immutable, next node is a new instance
- No "prev" parameter or state stack - `self` IS the complete state
- Terminal nodes return `None` to end the graph

## Key Abstractions

**Node:**
- Purpose: Represents a step in agent reasoning; holds both state and routing logic
- Examples: `Start(query=str)`, `Process(task=str)`, `Review(content=str)` from tests
- Pattern: Subclass `Node`, define fields as Pydantic fields, implement `__call__(lm: LM) -> NextNodeType | AnotherType | None`

**Graph:**
- Purpose: Discovers reachable nodes from type hints; runs execution loop safely
- Examples: `graph = Graph(start=AnalyzeRequest)`
- Pattern: Walk return type hints from start node using BFS; cache adjacency list in `_nodes`

**LM (Language Model):**
- Purpose: Protocol for producing typed node instances
- Pattern: Implement `make(node: Node, target: type[T]) -> T` and `decide(node: Node) -> Node | None`

**Backend:**
- Purpose: Concrete LM implementation (pydantic-ai or Claude CLI)
- Examples: `PydanticAIBackend(model="claude-sonnet")`, `ClaudeCLIBackend(model="claude-sonnet-4-20250514")`
- Pattern: Accept node and target type(s), convert to prompt, call LLM, parse response

## Entry Points

**Graph.run():**
- Location: `bae/graph.py:100-128`
- Triggers: User calls `graph.run(start_node_instance, lm_backend)`
- Responsibilities: Execute step-by-step, call `node(lm=lm)`, track steps, raise on max_steps exceeded

**Node.__call__():**
- Location: `bae/node.py:92-105`
- Triggers: Graph calls node instance as callable
- Responsibilities: Implement routing logic, call `lm.make()` or `lm.decide()`, return next node or None

**LM.make():**
- Location: `bae/lm.py:27-29` (protocol), implemented in backends
- Triggers: Node's `__call__` calls `lm.make(self, TargetType)`
- Responsibilities: Produce instance of specific target type; include current node state in prompt

**LM.decide():**
- Location: `bae/lm.py:31-33` (protocol), implemented in backends
- Triggers: Node's `__call__` calls `lm.decide(self)`
- Responsibilities: Extract successor types from node's return hint, let LLM choose, produce chosen node

## Error Handling

**Strategy:** Exceptions for invalid configurations; RuntimeError for execution failures

**Patterns:**
- `Node.successors()` and `Node.is_terminal()` raise nothing but can return empty set
- `Graph.validate()` returns list of warnings/errors (does not raise)
- `Graph.run()` raises `RuntimeError` if max_steps exceeded
- `LM.decide()` raises `ValueError` if node has no successors and is not terminal
- Backend `_run_cli()` raises `RuntimeError` on subprocess timeout or JSON parse failure

## Cross-Cutting Concerns

**Logging:** Not implemented; nodes use docstrings and field values for context

**Validation:** Pydantic handles field validation at node instantiation; Graph validates topology

**Authentication:** Delegated to LM backends:
- `PydanticAIBackend`: Inherits auth from pydantic-ai/ANTHROPIC_API_KEY
- `ClaudeCLIBackend`: Inherits auth from Claude CLI tool (external)

**Type System:**
- Nodes are Pydantic BaseModel subclasses - fields are validated on construction
- Return type hints use Python's union syntax (`A | B | None`) for declaring successors
- Requires Python 3.14+ for forward references to work without `from __future__ import annotations`

---

*Architecture analysis: 2026-02-04*
