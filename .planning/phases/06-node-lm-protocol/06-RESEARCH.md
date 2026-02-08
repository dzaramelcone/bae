# Phase 6: Node & LM Protocol - Research

**Researched:** 2026-02-07
**Domain:** Node API contract, LM protocol redesign, field classification, Pydantic patterns
**Confidence:** HIGH

## Summary

Phase 6 transforms bae's node API from "nodes call LM explicitly" to "nodes declare fields, bae fills them." The core shift: `__call__` no longer takes `lm` as a required parameter (it's opt-in for escape hatch), and the LM protocol changes from `make`/`decide` to `choose_type`/`fill` -- separating "which type next?" from "populate its fields."

The existing codebase already has all the building blocks: `_has_ellipsis_body()` for body detection, `classify_fields()` for field categorization, `_get_routing_strategy()` for routing decisions, and `GraphResult` for wrapping results. The work is restructuring these into the new contract and wiring `classify_fields()` output into signature generation so the LM sees Dep/Recall fields as InputFields (context) and plain fields as OutputFields (what to generate).

This phase does NOT wire the new protocol into `Graph.run()` -- that's Phase 7 (Integration). Phase 6 defines and tests the contracts in isolation: NodeConfig, the LM protocol methods, field-to-signature mapping, and start/terminal node semantics.

**Primary recommendation:** Build the new LM protocol (`choose_type`/`fill`) as new methods on the `LM` Protocol class alongside the existing `make`/`decide`. Don't remove `make`/`decide` yet -- Phase 8 (Cleanup) handles that. The new `node_config` attribute should be a separate `ClassVar` using a simple TypedDict, NOT extending Pydantic's `ConfigDict`.

## Standard Stack

### Core (Already in Project)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | >=2.0 | Node base class (BaseModel) | Already the foundation; ClassVar, model_construct, get_type_hints |
| dspy | >=2.0 | Signature generation, Predict, InputField/OutputField | Already used for signature generation and optimization |
| Python 3.14 | 3.14+ | PEP 649 deferred annotations, PEP 696 TypeVar defaults | Already required by project |

### Supporting (Already in Project)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-ai | >=0.1 | format_as_xml for prompt building | Used by PydanticAIBackend and ClaudeCLIBackend |
| incant | >=1.0 | Dep param injection in __call__ | Still needed for v1 compat in escape hatch; removed in Phase 7 |

### No New Dependencies Needed

This phase uses only Python stdlib + existing deps. No new libraries required.

## Architecture Patterns

### Current vs. New Architecture

**Current (v1):**
```
Node.__call__(self, lm: LM) -> NextNode | None    # lm is required
graph.run() calls node.__call__(lm=lm)             # always passes lm
LM.make(node, target_type) -> target instance       # single method
LM.decide(node) -> node | None                      # combined choose+fill
```

**New (v2):**
```
Node.__call__(self) -> NextNode | None              # lm not in signature (unless escape hatch)
Node.__call__(self, lm: LM) -> NextNode | None      # opt-in: lm injected if declared
graph.run() detects ... body -> auto fill+route      # bae handles everything
graph.run() detects custom body -> call with/without lm  # escape hatch
LM.choose_type(types, context) -> chosen_type        # step 1: pick type
LM.fill(target_type, context) -> instance            # step 2: populate fields
```

### Pattern 1: NodeConfig as Separate ClassVar

**What:** A TypedDict-based config class for per-node LM overrides, stored as a ClassVar.
**Confidence:** HIGH -- directly mirrors Pydantic's model_config pattern.

Pydantic's `model_config` is a `ClassVar[ConfigDict]` where `ConfigDict` is a `TypedDict`. We follow the same pattern but with a SEPARATE attribute name to avoid conflicts.

**Current code has a problem:** `NodeConfig` currently EXTENDS `ConfigDict`:
```python
class NodeConfig(ConfigDict, total=False):
    model: str
    temperature: float
```
And it's used AS `model_config`:
```python
class Node(BaseModel, arbitrary_types_allowed=True):
    model_config: ClassVar[NodeConfig] = NodeConfig()
```

This conflates Pydantic config with node-specific config. The CONTEXT.md decision says `node_config = NodeConfig(lm=...)` -- a SEPARATE attribute.

**New design:**
```python
from typing import ClassVar, TypedDict, TYPE_CHECKING

if TYPE_CHECKING:
    from bae.lm import LM

class NodeConfig(TypedDict, total=False):
    """Per-node configuration. Follows Pydantic's model_config naming convention."""
    lm: LM  # Per-node LM override

class Node(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    node_config: ClassVar[NodeConfig] = NodeConfig()
```

Key points:
- `NodeConfig` is a plain `TypedDict`, NOT extending `ConfigDict`
- `node_config` is `ClassVar[NodeConfig]` so Pydantic ignores it (not a model field)
- `model_config` reverts to standard Pydantic usage (just `ConfigDict`)
- `total=False` means all keys are optional -- no `node_config` = empty dict = inherit graph-level LM

### Pattern 2: LM Protocol -- choose_type() / fill()

**What:** The new LM protocol separates type selection from field population.
**Confidence:** HIGH -- based on existing codebase patterns.

The current `decide()` method does both "pick the type" and "fill its fields" in one call. The new protocol separates these concerns, which maps cleanly to the existing two-step pattern already used in `ClaudeCLIBackend.decide()` and `DSPyBackend.decide()`.

**Recommended signatures:**

```python
class LM(Protocol):
    def choose_type(
        self,
        types: list[type[Node]],
        context: dict[str, object],
    ) -> type[Node]:
        """Pick successor type from candidates, given resolved context fields.

        Args:
            types: Concrete Node types to choose from (no None -- caller handles terminal).
            context: Dict of resolved field name -> value (Dep + Recall fields).

        Returns:
            One of the types from the list.
        """
        ...

    def fill(
        self,
        target: type[T],
        context: dict[str, object],
        instruction: str,
    ) -> T:
        """Populate a node's plain fields given resolved context.

        Args:
            target: The Node subclass to instantiate.
            context: Dict of resolved field name -> value (InputFields for the LM).
            instruction: The node class name (+ optional docstring).

        Returns:
            An instance of target with plain fields filled by the LM.
        """
        ...
```

**Why this shape:**
- `context` is a `dict[str, object]` because `resolve_fields()` already returns exactly this format
- `instruction` is the node class name (NODE-04 requirement)
- `types` is a flat list (no None) because terminal detection is the graph's job, not the LM's
- `fill()` takes `target` type + context, not a node instance -- the LM creates the instance

**Backward compatibility:** Keep `make`/`decide` on the Protocol for now. Phase 8 removes them. Backends implement both old and new methods during transition.

### Pattern 3: Ellipsis Body Detection (Existing, Reuse)

**What:** `_has_ellipsis_body()` already exists in `bae/node.py` and works correctly.
**Confidence:** HIGH -- verified by existing tests in `test_auto_routing.py`.

The existing implementation uses `inspect.getsource()` + `ast.parse()` to detect `...` body. It correctly handles:
- Pure ellipsis body: `def __call__(self) -> X: ...`
- Docstring + ellipsis: `def __call__(self) -> X: """doc""" ...`
- Custom logic: returns False for any non-ellipsis body

**Recommendation:** Reuse as-is. No changes needed.

### Pattern 4: LM Parameter Detection (opt-in injection)

**What:** Detect if `__call__` declares `lm: LM` parameter.
**Confidence:** HIGH -- straightforward `inspect.signature` usage.

```python
import inspect

def _wants_lm(method) -> bool:
    """Check if __call__ declares an 'lm' parameter."""
    sig = inspect.signature(method)
    return "lm" in sig.parameters
```

This is simple and reliable. When `_wants_lm` returns True AND the node has custom logic (not `...` body), `graph.run()` passes the LM. When it returns False, bae doesn't inject LM.

For `...` body nodes, `_wants_lm` doesn't matter -- bae handles everything automatically. But users may still declare `lm` in their ellipsis-body `__call__` for type-hint purposes (the return type), and bae won't break.

### Pattern 5: Graph[T] Optional Generic

**What:** `Graph` optionally accepts a terminal type parameter for typed `GraphResult.result`.
**Confidence:** HIGH -- PEP 696 TypeVar defaults are available in Python 3.13+, bae requires 3.14+.

```python
from typing import TypeVar, Generic

T = TypeVar("T", bound=Node, default=Node)

class Graph(Generic[T]):
    """Agent graph. Optionally generic for typed terminal result."""
    ...

class GraphResult(Generic[T]):
    """Result of graph execution."""
    result: T | None  # typed as T when Graph[T] used, Node when bare Graph
    trace: list[Node]
```

**Usage:**
```python
# Untyped (result is Node | None)
graph = Graph(start=Start)

# Typed (result is MyTerminal | None)
graph = Graph[MyTerminal](start=Start)
result = graph.run(Start(query="hi"), lm=lm)
reveal_type(result.result)  # MyTerminal | None
```

**Important caveat:** The generic parameter is a TYPE-LEVEL feature only. At runtime, `Graph()` and `Graph[MyTerminal]()` behave identically. The value is in static type checking and IDE autocompletion, not runtime behavior.

### Pattern 6: Start Node Detection

**What:** Detect which node is the graph's start node (needed for NODE-02: start fields are caller-provided).
**Confidence:** HIGH -- the graph already knows its start node.

The `Graph` class already stores `self.start` as the start node type. No topology analysis needed -- the user tells us at construction time: `Graph(start=MyStartNode)`.

For field classification purposes:
- Start node: plain fields = caller-provided input (not LLM-filled)
- Non-start nodes: plain fields = LLM-filled
- All nodes: Dep fields = resolved by bae, Recall fields = searched from trace

This distinction is important for `node_to_signature()`: a start node's plain fields should NOT be OutputFields (the LM doesn't fill them).

### Pattern 7: node_to_signature() Redesign

**What:** Map `classify_fields()` output to DSPy InputField/OutputField.
**Confidence:** HIGH -- clean mapping from existing infrastructure.

Current `node_to_signature()` uses `Context` marker to identify InputFields. The new version uses `classify_fields()`:

```python
def node_to_signature(node_cls: type[Node], *, is_start: bool = False) -> type[dspy.Signature]:
    """Convert Node class to DSPy Signature using field classification.

    Field mapping:
    - Dep fields -> InputField (context from external sources)
    - Recall fields -> InputField (context from trace)
    - Plain fields on start node -> InputField (caller-provided context)
    - Plain fields on non-start node -> OutputField (LLM fills these)

    Instruction: node class name (+ docstring if present)
    """
    classifications = classify_fields(node_cls)
    hints = get_type_hints(node_cls, include_extras=True)
    fields = {}

    for name, cls_type in classifications.items():
        base_type = _get_base_type(hints[name])

        if cls_type in ("dep", "recall"):
            # Context for the LM (InputField)
            fields[name] = (base_type, dspy.InputField())
        elif is_start:
            # Start node plain fields are also InputFields (caller-provided)
            fields[name] = (base_type, dspy.InputField())
        else:
            # Non-start plain fields are OutputFields (LLM fills)
            fields[name] = (base_type, dspy.OutputField())

    instruction = node_cls.__name__
    if node_cls.__doc__:
        instruction += f": {node_cls.__doc__.strip()}"

    return dspy.make_signature(fields, instruction)
```

### Anti-Patterns to Avoid

- **Don't conflate NodeConfig with Pydantic's ConfigDict:** They serve different purposes. NodeConfig is for bae's per-node overrides, ConfigDict is for Pydantic's model behavior. Keep them separate.
- **Don't remove make/decide yet:** v1 tests depend on them. Phase 8 removes them.
- **Don't wire into Graph.run() yet:** Phase 6 defines the contracts. Phase 7 integrates them into the execution loop.
- **Don't make `lm` param detection clever:** A simple `"lm" in sig.parameters` is sufficient. Don't try to type-check the annotation or match against the LM Protocol.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Field classification | Custom hint walker | `classify_fields()` from Phase 5 | Already handles Dep, Recall, plain; skips "return" |
| Type hint extraction | Manual Annotated parsing | `get_type_hints(cls, include_extras=True)` + `get_args` | Handles forward refs, Annotated metadata |
| Dep/Recall resolution | Custom resolver | `resolve_fields()` from Phase 5 | Handles DAG ordering, caching, trace search |
| Ellipsis body detection | Custom source parser | `_has_ellipsis_body()` from node.py | Already tested, handles docstrings |
| TypeVar default generic | Complex overload patterns | PEP 696 `TypeVar("T", default=Node)` | Python 3.14 has native support |
| DSPy Signature creation | Manual class generation | `dspy.make_signature(fields, instruction)` | Standard DSPy API |

**Key insight:** Phase 5 built `classify_fields()` and `resolve_fields()` specifically so this phase can consume them. The bridge from field classification to DSPy signatures is the main new code.

## Common Pitfalls

### Pitfall 1: NodeConfig Conflicting with Pydantic's model_config

**What goes wrong:** If `NodeConfig` extends `ConfigDict`, Pydantic may interpret custom keys as Pydantic config, causing warnings or unexpected behavior. If `node_config` shadows `model_config`, Pydantic's internal config handling breaks.
**Why it happens:** The current code already does this -- `NodeConfig(ConfigDict, total=False)` extends Pydantic's TypedDict. This worked because the only keys were `model` and `temperature`, which aren't Pydantic config keys. But adding `lm` could cause issues.
**How to avoid:** Make `NodeConfig` a standalone `TypedDict`, not extending `ConfigDict`. Use `node_config` as the attribute name (not `model_config`). Annotate as `ClassVar[NodeConfig]` so Pydantic skips it.
**Warning signs:** Pydantic validation errors on node construction, or config keys silently ignored.

### Pitfall 2: ClassVar Not Properly Inherited

**What goes wrong:** A subclass that doesn't declare `node_config` may not inherit the parent's value, or may share a mutable reference.
**Why it happens:** Python ClassVar inheritance works for immutable values (ints, strings) but mutable dicts can be shared unintentionally.
**How to avoid:** `NodeConfig` is a `TypedDict` (immutable at the type level). Default `NodeConfig()` creates an empty dict. Subclass lookup should use `getattr(cls, 'node_config', {})` to handle missing case.
**Warning signs:** Nodes sharing config when they shouldn't, or config changes leaking between node classes.

### Pitfall 3: Breaking Existing Tests During Transition

**What goes wrong:** Changing `Node.__call__` signature or `LM` Protocol breaks all existing tests that use MockLM with `make`/`decide`.
**Why it happens:** Existing tests construct MockLM with `make()` and `decide()` methods. If the Protocol changes, all mocks break.
**How to avoid:** Add `choose_type`/`fill` as NEW methods alongside `make`/`decide`. Don't remove old methods. Phase 8 handles the migration.
**Warning signs:** Import errors, test failures in unrelated test files.

### Pitfall 4: Start Node Plain Fields Incorrectly Treated as LLM Output

**What goes wrong:** `node_to_signature()` marks start node plain fields as OutputFields, causing the LM to try to generate values for caller-provided inputs.
**Why it happens:** The `is_start` parameter is easy to forget or misuse.
**How to avoid:** `node_to_signature()` MUST accept an `is_start` parameter. The graph must pass it correctly when generating signatures. Tests must cover both start and non-start cases.
**Warning signs:** Start node fields appearing in DSPy OutputFields.

### Pitfall 5: Terminal Node Semantics in GraphResult

**What goes wrong:** `GraphResult.node` currently returns `Node | None` where None means "graph terminated." With the new design, the terminal node IS the result -- returning None loses the response data.
**Why it happens:** Current `Graph.run()` returns None when a terminal node's `__call__` returns None.
**How to avoid:** `GraphResult` needs a `.result` property that returns the terminal node (last item in trace), not None. The `.node` attribute changes semantics or is replaced. `.trace` should include the terminal node.
**Warning signs:** Losing terminal node data, empty GraphResult after successful execution.

### Pitfall 6: Confusing `__call__` Contract Between Auto and Escape Hatch

**What goes wrong:** Users expect `lm` to be available in `...` body nodes, or expect bae to auto-fill in custom body nodes.
**Why it happens:** The two modes have different contracts that aren't obvious from looking at a single node.
**How to avoid:** Clear documentation. Auto-routing (`...` body) = bae does everything, user doesn't need `lm`. Custom body = user takes full control, can opt into `lm` by declaring the parameter.
**Warning signs:** Users writing `...` body with `lm` param expecting to use it, or custom body users expecting auto-fill.

## Code Examples

### Example 1: Node with New API (v2)

```python
from typing import Annotated
from bae import Node, Dep, Recall

def get_weather(city: str) -> str:
    return f"Sunny in {city}"

class PlanTrip(Node):
    """Plan a trip itinerary based on destination and weather."""
    # Caller provides (start node)
    destination: str

    def __call__(self) -> DayPlan | None:
        ...  # bae handles: resolve deps, fill plain fields, route

class DayPlan(Node):
    """Plan activities for a single day."""
    # Dep-resolved (InputField for LM)
    weather: Annotated[str, Dep(get_weather)]
    # Recalled from trace (InputField for LM)
    destination: Annotated[str, Recall()]
    # LLM fills these (OutputFields)
    morning: str
    afternoon: str
    evening: str

    def __call__(self) -> DayPlan | None:
        ...  # bae routes

class TripSummary(Node):
    """Summarize the complete trip plan."""  # Terminal -- fields ARE the response
    itinerary: str
    total_days: int

    def __call__(self) -> None:
        ...
```

### Example 2: Escape Hatch with opt-in LM

```python
from bae import Node, LM

class SmartRouter(Node):
    """Route based on custom business logic, with LM fallback."""
    query: str

    def __call__(self, lm: LM) -> FastPath | SlowPath:
        # Custom logic -- user takes control
        if self.is_simple_query():
            return FastPath(result=self.quick_answer())
        # Use LM for complex cases
        chosen = lm.choose_type([FastPath, SlowPath], {"query": self.query})
        return lm.fill(chosen, {"query": self.query}, instruction="SmartRouter")

    def is_simple_query(self) -> bool:
        return len(self.query.split()) < 5
```

### Example 3: NodeConfig Per-Node LM Override

```python
from typing import ClassVar
from bae import Node, NodeConfig
from bae.lm import SomeLMBackend

class CheapNode(Node):
    """A node that uses a cheaper model."""
    node_config: ClassVar[NodeConfig] = NodeConfig(lm=SomeLMBackend(model="haiku"))
    data: str

    def __call__(self) -> ExpensiveNode:
        ...

class ExpensiveNode(Node):
    """A node that inherits the graph-level LM (no override)."""
    analysis: str
    recommendation: str

    def __call__(self) -> None:
        ...
```

### Example 4: Graph[T] Optional Generic

```python
from bae import Graph, GraphResult

# Untyped -- result.result is Node | None
graph = Graph(start=PlanTrip)
result = graph.run(PlanTrip(destination="Tokyo"), lm=my_lm)
terminal = result.result  # type: Node | None

# Typed -- result.result is TripSummary | None
graph = Graph[TripSummary](start=PlanTrip)
result = graph.run(PlanTrip(destination="Tokyo"), lm=my_lm)
terminal = result.result  # type: TripSummary | None
```

### Example 5: Field Classification -> Signature Generation

```python
from bae.resolver import classify_fields

class DayPlan(Node):
    weather: Annotated[str, Dep(get_weather)]   # -> "dep"
    destination: Annotated[str, Recall()]        # -> "recall"
    morning: str                                  # -> "plain"
    afternoon: str                                # -> "plain"

classifications = classify_fields(DayPlan)
# {'weather': 'dep', 'destination': 'recall', 'morning': 'plain', 'afternoon': 'plain'}

# For non-start node:
# weather -> InputField (context)
# destination -> InputField (context)
# morning -> OutputField (LLM fills)
# afternoon -> OutputField (LLM fills)
```

## State of the Art

| Old Approach (v1) | New Approach (v2) | Changed In | Impact |
|-------|---------|---------|------|
| `Context()` marker for InputFields | `classify_fields()` determines InputField/OutputField | Phase 6 | `Context` marker becomes redundant |
| `__call__(self, lm: LM)` required | `__call__(self)` default, `lm` opt-in | Phase 6 | Nodes don't need to know about LM |
| `lm.make(node, target)` / `lm.decide(node)` | `lm.choose_type(types, context)` / `lm.fill(target, context, instruction)` | Phase 6 | Cleaner separation of concerns |
| `NodeConfig(ConfigDict, total=False)` | `NodeConfig(TypedDict, total=False)` standalone | Phase 6 | No Pydantic config conflation |
| `GraphResult(node=None)` for terminal | `GraphResult(result=terminal_node)` | Phase 6 | Terminal node data preserved |
| `model_config: ClassVar[NodeConfig]` on Node | `node_config: ClassVar[NodeConfig]` separate from `model_config` | Phase 6 | Clean separation |

**Deprecated in this phase (removed in Phase 8):**
- `Context` marker (replaced by classify_fields)
- `Bind` marker (replaced by Recall)
- `LM.make()` / `LM.decide()` (replaced by choose_type/fill)
- `model`/`temperature` keys on NodeConfig (replaced by `lm` key)

## Open Questions

### 1. GraphResult.result vs GraphResult.node naming

**What we know:** Current `GraphResult.node` is `Node | None` where None means terminated. New design needs the terminal node to be the result.
**What's unclear:** Should we rename `.node` to `.result`? Or add `.result` and deprecate `.node`? Or change `.node` semantics to always hold the terminal node?
**Recommendation:** Add `.result` property that returns the last node in trace (the terminal node). Keep `.node` for backward compat but consider deprecation. The `trace` already contains the terminal node as the last element. `.result` just accesses `trace[-1]` with proper typing when `Graph[T]` is used.

### 2. How NodeConfig LM override interacts with choose_type/fill

**What we know:** `node_config = NodeConfig(lm=custom_lm)` should override the graph-level LM for that node.
**What's unclear:** Does the override apply to both `choose_type()` and `fill()`? Or could a node override just the fill LM but use graph-level for routing?
**Recommendation:** Override both. `NodeConfig.lm` replaces the entire LM for that node. If we need finer control later, we can add `choose_type_lm` and `fill_lm` keys to NodeConfig, but YAGNI for now.

### 3. How choose_type handles single-type returns

**What we know:** Current `_get_routing_strategy` returns "make" for single-type, "decide" for union.
**What's unclear:** Should `choose_type()` be called for single-type returns, or should bae skip it?
**Recommendation:** bae should skip `choose_type()` for single-type returns. If there's only one option, there's nothing to choose. Call `fill()` directly. This matches the current "make" strategy.

### 4. Base Node.__call__ default implementation

**What we know:** Current `Node.__call__` has a default implementation: `return lm.decide(self)`. The new contract says `...` body = auto-routing.
**What's unclear:** What should the BASE `Node.__call__` do? Should it have a default implementation, or should it be abstract?
**Recommendation:** Base `Node.__call__` should raise `NotImplementedError` or have `...` body. Since `...` body means "auto-route," the base class could use `...` as its body. But that would make ALL nodes auto-routed by default, which might surprise users who expect to write custom logic. Better: keep a default that raises `NotImplementedError("Override __call__ with ... for auto-routing or custom logic")`.

## Sources

### Primary (HIGH confidence)
- **Existing codebase** -- bae/node.py, bae/graph.py, bae/lm.py, bae/markers.py, bae/resolver.py, bae/compiler.py, bae/dspy_backend.py, bae/result.py, all test files
- **Phase 5 output** -- classify_fields(), resolve_fields(), build_dep_dag(), recall_from_trace(), validate_node_deps()
- **CONTEXT.md** -- Locked decisions for __call__ contract, NodeConfig shape, terminal as response
- **Python docs** -- inspect.signature, ast module, ClassVar, TypeVar

### Secondary (MEDIUM confidence)
- [Pydantic ConfigDict docs](https://docs.pydantic.dev/latest/api/config/) -- ConfigDict is TypedDict; model_config is ClassVar
- [PEP 696 -- TypeVar defaults](https://peps.python.org/pep-0696/) -- Available Python 3.13+, `TypeVar("T", default=Node)` pattern
- [Pydantic model_config ClassVar handling](https://docs.pydantic.dev/latest/concepts/models/) -- ClassVar attributes skipped by Pydantic field processing
- [Extending ConfigDict discussion](https://github.com/pydantic/pydantic/discussions/10419) -- Separate config approach recommended over extending ConfigDict
- [DSPy Signature API](https://dspy.ai/learn/programming/signatures/) -- InputField, OutputField, make_signature

### Tertiary (LOW confidence)
- None -- all findings verified against codebase or official docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing
- Architecture: HIGH -- patterns derived from existing codebase + locked decisions
- Pitfalls: HIGH -- identified from actual code review, not speculation
- Code examples: HIGH -- based on existing API patterns and locked decisions
- Open questions: MEDIUM -- genuine ambiguities that need planner/implementer judgment

**Research date:** 2026-02-07
**Valid until:** Indefinite (internal project, no external API changes)
