# Feature Landscape: Context Frames & Dependency Injection for Bae v2

**Domain:** Dependency injection, execution trace recall, and context frame patterns in agent/workflow frameworks
**Researched:** 2026-02-07
**Confidence:** HIGH (verified against official docs for FastAPI, PydanticAI, LangGraph, DSPy, Dagster)

## Framework Survey

How each framework handles the patterns bae v2 is building.

### FastAPI `Depends()` -- Closest Pattern to Bae's `Dep`

**How it works:**
- `Annotated[dict, Depends(common_parameters)]` declares a dependency
- FastAPI inspects the callable passed to `Depends()`, resolves its parameters recursively
- Dependencies can have sub-dependencies (chaining) -- FastAPI builds a tree and resolves bottom-up
- Results cached per-request by default (same dep function called once even if used in multiple places)
- No registration needed -- just pass the function reference to `Depends()`
- Supports both async and sync dependency functions freely mixed

**Dep chaining pattern:**
```python
async def get_db() -> Database: ...
async def get_user(db: Database = Depends(get_db)) -> User: ...
async def get_permissions(user: User = Depends(get_user)) -> Permissions: ...

@app.get("/items/")
async def read_items(perms: Annotated[Permissions, Depends(get_permissions)]):
    ...  # FastAPI resolves: get_db -> get_user -> get_permissions
```

**Key insight for bae:** FastAPI's `Depends()` takes a *callable* and resolves its params recursively. Bae's `Dep(get_weather)` is the same pattern -- the framework calls the function, resolving its own deps first. The recursive resolution via topological sort is table stakes in this pattern.

**Confidence:** HIGH (verified via official FastAPI docs)

### PydanticAI `RunContext[DepsT]` -- Deps as Typed Container

**How it works:**
- Agent declares `deps_type=MyDeps` (a dataclass or Pydantic model)
- At runtime: `agent.run("prompt", deps=MyDeps(api_key="...", client=httpx_client))`
- Tools, system prompts, validators receive `RunContext[DepsT]` as first param
- Framework introspects function signatures to detect if they want `RunContext`
- `RunContext` provides: `deps`, `model`, `run_id`, `usage`, `run_step`, `timestamp`
- Override pattern for testing: `with agent.override(deps=test_deps):`

**Key differences from bae's approach:**
- PydanticAI uses a *single container object* for all deps, not per-field injection
- No dep chaining -- you build the container yourself before `run()`
- No execution trace recall -- RunContext doesn't look backward at prior results
- Type safety is at the container level, not the individual field level

**Key insight for bae:** PydanticAI's approach is simpler but less powerful. The per-field `Dep` annotation in bae v2 is more granular -- each field declares exactly what it needs and how to get it, rather than stuffing everything into one bag. This is a genuine differentiator.

**Confidence:** HIGH (verified via official PydanticAI docs and DeepWiki)

### LangGraph -- State-as-TypedDict, InjectedState, Runtime

**How state works:**
- State defined as `TypedDict` or Pydantic model -- the contract between all nodes
- Every node receives the full state, returns a partial update dict
- Reducer functions define how updates merge (e.g., `messages: Annotated[list, add_messages]`)
- Checkpointing saves state between steps for replay/debugging

**How dependency injection works:**
- `InjectedState`: `state: Annotated[dict, InjectedState]` -- injects graph state into tools without exposing it to the LLM
- `InjectedState("messages")`: inject specific state fields, not the whole dict
- `Runtime` object: provides `Context` (user_id, db connections), `Store` (long-term memory), `StreamWriter`
- Runtime context defined via `context_schema` dataclass, passed at invocation time
- `ToolRuntime` parameter in tools for accessing Runtime

**Key differences from bae:**
- LangGraph state is a mutable shared dict, not typed fields on node classes
- All nodes see the same state -- no per-node field assembly
- InjectedState is for tools (hiding params from LLM), not for node fields
- No dep chaining -- Runtime context is a flat container

**Key insight for bae:** LangGraph's state model is "shared mutable dict with reducers." Bae's model is "each node is a typed frame with independently resolved fields." The LangGraph approach requires all nodes to agree on a single state schema. Bae's approach lets each node declare only what it needs. This is both a differentiator and a design risk (more complex resolution).

**Confidence:** HIGH (verified via LangChain docs, GitHub issues)

### DSPy -- Module Composition and Trace

**How modules work:**
- Subclass `dspy.Module`, declare sub-modules in `__init__`, call them in `forward()`
- No dependency injection -- modules are composed manually via Python code
- Trace is collected automatically during `forward()` execution at compile time
- Optimizers run the program many times, collect I/O traces, filter by metric
- Traces capture: inputs per module, outputs per module, execution order

**How trace works for optimization:**
- Each `Predict` call internally logs its inputs and outputs when in compile mode
- Optimizers (BootstrapFewShot, MIPROv2, GEPA) use these traces to:
  - Select good few-shot demonstrations
  - Propose better instructions
  - Reflect on predictor behavior
- Traces are per-module, not per-graph -- each Predict has its own trace

**Key insight for bae:** DSPy's trace is purpose-built for optimization, not for runtime state recall. Bae's `Recall()` marker is conceptually different -- it's about runtime state lookup ("find me the WeatherResult from earlier in this execution"), not about collecting training data. However, the *structure* of the trace (typed I/O per node) is similar, and bae could leverage it for both purposes.

**Confidence:** HIGH (verified via official DSPy docs)

### Prefect -- Task Dependencies via Return Values

**How it works:**
- Tasks are decorated Python functions
- Data flows between tasks by passing return values as arguments
- Prefect auto-detects dependencies when a task result is passed as a parameter
- For distributed execution, results go through storage (S3, filesystem)
- No explicit dependency declaration -- the dependency graph is implicit from data flow

**Key insight for bae:** Prefect's "just pass return values" pattern is the simplest model. Bae's Bind/Dep pattern in v1 is similar but more explicit. The v2 Dep(callable) pattern adds framework-managed resolution on top.

**Confidence:** MEDIUM (WebSearch-verified, no official doc deep-dive)

### Dagster -- Resources as Type-Annotated Parameters

**How it works:**
- Resources inherit from `ConfigurableResource` with typed config fields
- Assets declare resource needs via type annotations: `def my_asset(db: DatabaseResource):`
- Resources registered centrally in `Definitions(resources={"db": DatabaseResource(...)})`
- IO Managers handle data persistence between assets
- Clean separation: assets declare needs, infrastructure provides them

**Key insight for bae:** Dagster's pattern of "declare what you need by type annotation, framework resolves it" is exactly what bae v2 is doing with `Annotated[WeatherResult, Dep(get_weather)]`. The main difference is bae's deps also include a *callable* for producing the value, while Dagster's are pre-registered resources.

**Confidence:** MEDIUM (verified via Dagster blog, official docs overview)

---

## Table Stakes

Features that are expected/required for the dep injection, trace recall, and context frame patterns to work correctly. Missing = the system feels broken or unusable.

| Feature | Why Expected | Complexity | Existing in v1? | Notes |
|---------|--------------|------------|-----------------|-------|
| **Type-based dependency resolution** | Core pattern in FastAPI, PydanticAI, Dagster. Users expect deps matched by type. | Low | YES (incant + Dep marker) | Already works. v2 changes the annotation syntax but keeps type matching. |
| **Clear error on missing deps** | FastAPI, Dagster, PydanticAI all give clear errors. Users expect to know what's missing. | Low | YES (BaeError with type name) | Keep this. Error messages should name the missing type and the node that needs it. |
| **Dep callable invocation** | FastAPI `Depends(fn)` is the canonical pattern. If you annotate `Dep(fn)`, the framework *must* call `fn`. | Med | NO (v1 Dep is a marker only) | Core v2 feature. Framework calls the fn and injects the result. |
| **Dep chaining (recursive resolution)** | FastAPI resolves sub-dependencies recursively. `Dep(fn)` where `fn` itself has deps is expected. | Med-High | NO | `def get_weather(location: LocationDep) -> WeatherResult` must resolve `location` first. Requires topological sort of dep graph. |
| **Caching within a single run** | FastAPI caches per-request. Same dep function should not be called twice in one graph run. | Med | NO | Important for expensive deps (API calls, DB queries). Cache by (function, resolved_args) tuple. |
| **Execution trace as list of typed nodes** | Every framework tracks execution history. LangGraph checkpoints, DSPy traces, Prefect task results. | Low | YES (GraphResult.trace) | Already have `trace: list[Node]`. v2 Recall() searches this. |
| **LLM fills unannotated fields** | Core bae identity. "No annotation = LLM fills it." Class name = instruction. | Low | YES (make/decide pattern) | Keep this. It's what makes nodes "context frames." |
| **Return type = output schema** | Type hints on `__call__` define successors. | Low | YES (successors from hints) | Keep this. |

## Differentiators

Features that set bae v2 apart from existing frameworks. Not expected by users coming from other tools, but provide genuine value.

| Feature | Value Proposition | Complexity | How Others Do It | Notes |
|---------|-------------------|------------|------------------|-------|
| **`Dep(callable)` on fields, not params** | Fields declare their own data sources. No separate `__call__` params needed for injection. The node class IS the dependency spec. | Med | FastAPI: `Depends()` on function params. PydanticAI: single `RunContext` container. LangGraph: shared state dict. Nobody does per-field dep callables on a model class. | This is the core v2 innovation. Each field says "I need X and here's how to get it." |
| **`Recall()` -- type-based trace search** | `Annotated[WeatherResult, Recall()]` searches execution trace for most recent matching type. No explicit data passing between nodes. | Med | LangGraph: explicit state dict keys. DSPy: manual `forward()` composition. Prefect: explicit return value passing. Nobody does type-based trace recall. | Novel pattern. Enables implicit data flow -- if an earlier node produced a `WeatherResult`, any later node can recall it by type. |
| **Node class name = LLM instruction** | `class AnalyzeUserIntent(Node):` -- the class name IS the prompt instruction. No docstrings or system prompts required. | Low | DSPy: docstrings as Instructions. PydanticAI: explicit system_prompt decorator. LangGraph: prompt templates. | Already in v1. Extremely clean DX. |
| **Fields as context frame** | Node fields = assembled prompt context. `Dep` fields are resolved, `Recall` fields are searched, unannotated fields are LLM-filled. The node IS the context window. | Med | LangGraph: shared TypedDict state. PydanticAI: RunContext container. DSPy: Signature I/O fields. None assemble context from heterogeneous field annotations. | This is the "context frame" pattern. Each node class declares exactly what context it needs, and the framework assembles it from different sources. |
| **Implicit service configuration (graph-level LM)** | LM configured at graph level, individual nodes can override via `model_config`. No `lm` param in every node. | Low | LangGraph: model passed at agent creation. DSPy: `dspy.configure(lm=...)` global. PydanticAI: model per agent. | Already partially in v1 (lm passed to run()). v2 makes graph-level config + per-node override explicit. |
| **Dep chaining across heterogeneous sources** | A dep callable's params can be other Dep types, Recall types, or plain values. The framework resolves across data sources. | High | FastAPI: chaining is same-source (all from request + other deps). Nobody chains across trace recall + callables + LLM-filled fields. | Unique to bae. `def get_forecast(weather: Annotated[WeatherResult, Recall()], location: LocationDep)` mixes recall and injection. |

## Anti-Features

Features to deliberately NOT build. Common mistakes when implementing these patterns.

| Anti-Feature | Why Avoid | What to Do Instead | Framework That Does It Wrong |
|--------------|-----------|-------------------|------------------------------|
| **Global mutable state dict** | Couples all nodes to one schema. Adding a field means touching the state definition. Bae's per-node model is better. | Each node declares its own fields. No shared state schema. | LangGraph (TypedDict state is exactly this anti-pattern for bae's design) |
| **Single deps container object** | Forces all deps into one bag. Loses the "each field declares its source" pattern. | Per-field `Dep(callable)` annotations. Each field is independent. | PydanticAI (RunContext[DepsT] is a single container) |
| **Automatic dep registration by type** | If the framework auto-registers any value of type X as a dep, you get ambient/spooky state. Deps should be explicitly declared. | Dep(callable) is explicit. Recall() searches the trace explicitly. No magic registration. | v1 Bind pattern (sets a value by type in a registry -- implicit) |
| **Eager resolution of all deps at graph start** | Wastes compute on deps that may never be reached. Some graph paths skip nodes entirely. | Resolve deps lazily, only when the node is about to execute. | (Not a common mistake, but important to avoid) |
| **Dep result mutation** | If a dep result is mutable and shared, one node's changes affect another's view. | Dep results should be treated as immutable snapshots. If mutation is needed, produce a new value. | LangGraph (shared mutable state dict) |
| **Implicit Recall with no trace** | If Recall() is used but no prior node produced that type, failing silently is dangerous. | Recall() on a type not in the trace should raise a clear error, like missing Dep. | -- |
| **Async dep resolution when graph is sync** | Bae is sync-only. Adding async dep resolution creates API inconsistency. | Keep dep resolution sync. Dep callables are sync functions. | -- |
| **Over-abstracting the dep resolution mechanism** | Building a plugin system for custom resolvers, provider hierarchies, scope levels. | Three sources: `Dep(callable)`, `Recall()`, and LLM-fill. That's it. No plugin architecture. | dependency-injector (over-engineered for bae's needs) |

## Feature Dependencies

```
Dep(callable) field annotation
    |
    +---> Type-based resolution (match field type to callable return type)
    |         |
    |         +---> Dep chaining (resolve callable's own deps first)
    |                   |
    |                   +---> Topological sort of dep graph (detect cycles)
    |                   |
    |                   +---> Caching (don't call same dep twice per run)
    |
    +---> Error handling (missing dep callable, wrong return type)

Recall() field annotation
    |
    +---> Trace search by type (scan GraphResult.trace for matching type)
    |         |
    |         +---> Recency semantics (most recent match? all matches?)
    |
    +---> Error handling (type not found in trace)

Context frame assembly (at node execution time)
    |
    +---> Resolve all Dep fields
    +---> Search trace for all Recall fields
    +---> Pass remaining fields to LLM for fill
    +---> Construct node instance with all fields populated
```

Key dependency chain:
1. `Dep(callable)` resolution must work before chaining can work
2. Chaining requires topological sort (cycle detection)
3. `Recall()` requires the execution trace to already exist (only works for non-first nodes)
4. Context frame assembly orchestrates all three sources (Dep, Recall, LLM)

## Cross-Framework Comparison Matrix

How each framework handles each concern:

| Concern | FastAPI | PydanticAI | LangGraph | DSPy | Dagster | **Bae v2** |
|---------|---------|------------|-----------|------|---------|-----------|
| **Dep declaration** | `Depends(fn)` on params | `deps_type=T` on agent | `InjectedState` on tools | Manual in `__init__` | Type annotation on params | `Dep(fn)` on fields |
| **Dep resolution** | Recursive, bottom-up | Flat (user builds container) | Flat (context schema) | None (manual) | By type from registry | Recursive via topo sort |
| **Dep chaining** | YES (sub-dependencies) | NO | NO | NO | NO (resources are flat) | YES (planned) |
| **Caching** | Per-request | N/A (user manages) | N/A | N/A | N/A | Per-run (planned) |
| **State passing** | Return values | RunContext container | Shared TypedDict | Module composition | IO Managers | Typed trace + Recall |
| **Trace/History** | N/A | Message history | Checkpoints | Compile-time traces | Asset lineage | `list[Node]` + Recall |
| **LLM integration** | None | Core (agent framework) | Core (graph framework) | Core (prompt compiler) | None | Core (context frames) |
| **Type safety** | Annotated types | Generic `RunContext[T]` | TypedDict | Signatures | Type annotations | Pydantic fields |

## MVP Recommendation

For MVP of the v2 context frame system, prioritize in this order:

### Phase 1: Foundation (table stakes)

1. **`Dep(callable)` basic resolution** -- Framework calls the callable and injects result into field
   - No chaining yet. Callables take no deps themselves.
   - Complexity: Medium
   - Depends on: Reworking how node instances are constructed

2. **`Recall()` basic resolution** -- Search trace for most recent instance of matching type
   - Return the value from the most recent node in trace that has a field of that type
   - Complexity: Medium
   - Depends on: Existing trace infrastructure (already built)

3. **Error messages** -- Clear errors for: missing dep callable fails, Recall type not in trace
   - Complexity: Low
   - Depends on: Items 1 and 2

### Phase 2: Power Features (differentiators)

4. **Dep chaining** -- Dep callables can declare their own deps via type annotations
   - Build dep graph, topological sort, resolve bottom-up
   - Detect cycles and raise clear errors
   - Complexity: Medium-High
   - Depends on: Phase 1 item 1

5. **Per-run caching** -- Same dep callable with same resolved args returns cached result
   - Important for expensive operations (API calls, DB queries)
   - Complexity: Medium
   - Depends on: Phase 1 item 1

6. **Context frame assembly** -- Orchestrate Dep, Recall, and LLM-fill into a single node construction step
   - This is where the "node as context frame" pattern fully materializes
   - Complexity: Medium-High
   - Depends on: All of Phase 1

### Defer to Post-MVP

- **Cross-source chaining** (dep callable that takes a Recall param): Novel but complex. Get basic chaining working first.
- **Dep callable async support**: Bae is sync-only. Don't add async.
- **Custom resolution strategies**: Three sources (Dep, Recall, LLM) are enough. No plugin system.
- **Recall with filters** (e.g., "recall WeatherResult from node named X"): Start with simple type matching.

## Key Insights From Research

### The Annotated Pattern is Standard

FastAPI, PydanticAI, LangGraph, and Dagster all use `Annotated[Type, Metadata]` for declaring injection points. Bae v2's `Annotated[WeatherResult, Dep(get_weather)]` is idiomatic Python. Users of any of these frameworks will recognize the pattern immediately.

### Nobody Does Per-Field Dep Resolution on Model Classes

This is bae's genuine innovation. Every other framework either:
- Injects deps into function parameters (FastAPI, Dagster)
- Provides a single container (PydanticAI RunContext)
- Uses shared mutable state (LangGraph TypedDict)
- Does manual composition (DSPy Module.forward())

Making Pydantic model fields the dep declaration site -- where each field independently declares how it gets its value -- is novel. This is what makes "node as context frame" work: the class definition IS the context specification.

### Dep Chaining is Rare but Powerful

Only FastAPI implements true recursive dep resolution. PydanticAI, LangGraph, Dagster, and DSPy all use flat dependency models. FastAPI's success with this pattern validates that it works well in practice, but the recursive resolution needs careful cycle detection and clear error messages.

### Trace Recall is Novel

No surveyed framework implements "search execution history by type and inject the result." LangGraph has checkpoints (for replay), DSPy has traces (for optimization), but neither supports "give me the last WeatherResult from wherever it appeared in the execution." This is bae's `Recall()` pattern, and it's genuinely new.

The closest analog is DSPy's trace inspection during optimization, where the optimizer looks at prior I/O to select demonstrations. But that's a compile-time operation, not runtime injection.

### Context Engineering Validates the Frame Pattern

Anthropic's September 2025 formalization of "context engineering" aligns with bae's approach: context is "the smallest set of high-signal tokens that maximize the likelihood of some desired outcome." Bae's context frame pattern -- where each node declares exactly what context it needs via typed fields -- is a clean implementation of this principle. Each field is a specific, typed context requirement with a declared source.

## Confidence Assessment

| Claim | Confidence | Reasoning |
|-------|------------|-----------|
| FastAPI Depends pattern is the closest analog to Dep(callable) | HIGH | Verified in official FastAPI docs. Same pattern: callable in annotation, recursive resolution. |
| No framework does per-field dep resolution on model classes | HIGH | Surveyed 5 frameworks. None use this pattern. |
| Recall() is novel (no framework does type-based trace search for injection) | HIGH | Surveyed 5 frameworks. Closest is DSPy trace but for optimization, not runtime injection. |
| Dep chaining via topological sort is table stakes for the pattern | HIGH | FastAPI does it. It's what users expect from recursive `Depends()`. |
| Per-run caching is important | MEDIUM | FastAPI caches per-request. Dagster has IO managers. Pattern is standard but bae's execution model is different (graph run vs HTTP request). |
| Context frame assembly (Dep + Recall + LLM-fill) will work in practice | MEDIUM | Each piece is proven individually. The combination is novel and needs validation. |
| Sync-only dep resolution is sufficient | HIGH | Bae is sync-only. FastAPI supports both but sync works fine for dep resolution. |

## Sources

**Official Documentation (HIGH confidence):**
- [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/) -- Depends() pattern, chaining, caching
- [PydanticAI Dependencies](https://ai.pydantic.dev/dependencies/) -- RunContext, deps_type, injection points
- [PydanticAI Architecture (DeepWiki)](https://deepwiki.com/pydantic/pydantic-ai/2.4-dependencies-and-run-context) -- Internal resolution mechanism
- [DSPy Modules](https://dspy.ai/learn/programming/modules/) -- Module composition, trace during forward()
- [DSPy Optimizers](https://dspy.ai/learn/optimization/optimizers/) -- How traces feed optimization
- [LangChain Runtime Docs](https://docs.langchain.com/oss/python/langchain/runtime) -- Runtime context injection
- [Dagster Resources](https://dagster.io/blog/a-practical-guide-to-dagster-resources) -- Type-annotated resource injection
- [Anthropic Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) -- Context as assembled frame

**Framework Source / Issues (MEDIUM confidence):**
- [LangGraph InjectedState issues](https://github.com/langchain-ai/langgraph/issues/6241) -- InjectedState behavior
- [LangGraph Runtime injection](https://github.com/langchain-ai/langgraph/issues/5990) -- Runtime dep pattern
- [incant docs](https://incant.threeofwands.com/en/stable/usage.html) -- Hook factory pattern (already used in bae v1)

**Community / WebSearch (LOW confidence, used for landscape only):**
- [Prefect vs Dagster comparison](https://www.decube.io/post/dagster-prefect-compare) -- Data passing patterns
- [Context Engineering Guide](https://www.promptingguide.ai/guides/context-engineering-guide) -- Context frame concepts

---

*Research conducted: 2026-02-07*
*Supersedes: 2026-02-04 FEATURES.md (which covered DSPy compilation only)*
