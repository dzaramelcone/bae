# Phase 28: Input Gates - Research

**Researched:** 2026-02-15
**Domain:** asyncio Future-based graph suspension with REPL input routing
**Confidence:** HIGH

## Summary

Phase 28 adds human-in-the-loop input gates to bae graphs running inside cortex. When a graph needs user input, execution suspends via `asyncio.Future` until the user responds through either GRAPH mode commands or a cross-mode shortcut. The entire feature builds on existing primitives: `asyncio.Future` for suspension, `dep_cache` for injection, `GraphState` enum for the WAITING state, `ToolbarConfig` for the badge widget, and `dispatch_graph` for the `input` command.

The core mechanism is an `InputGate` class (asyncio.Future wrapper with schema metadata) injected into graph execution via `dep_cache`. When a node's dep function awaits the gate, the graph coroutine suspends at the `await` inside `resolve_fields()`. The engine detects the pending gate, transitions the `GraphRun` to WAITING state, and emits a notification through the `[graph]` channel. The user resolves the gate by providing a value, which sets the Future result, and graph execution resumes from exactly where it paused.

**Primary recommendation:** Implement as a new `Gate` marker (sibling to `Dep`, `Recall`, `Effect`) that the resolver handles natively. The gate's Future is created and registered in the engine layer, then injected via `dep_cache` so `resolve_fields()` awaits it during dep resolution. This keeps the graph module clean and the suspension mechanism inside the engine/resolver boundary.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio.Future` | stdlib | Suspension primitive for input gates | Standard single-value awaitable. Unlike Event (bool flag), Future carries a typed result value. |
| `pydantic.fields.FieldInfo` | existing dep | Schema extraction for input prompts | Already used by `Graph._input_fields` for start node schema. Same introspection yields field name, type, description. |
| `prompt_toolkit` toolbar | existing dep | Badge widget for pending input count | `ToolbarConfig.add()` already supports arbitrary widgets. New widget queries pending gate count. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `typing.Annotated` | stdlib | `Gate` marker annotation on node fields | Same pattern as `Dep()`, `Recall()` -- `Annotated[str, Gate(description="...")]` |
| `json` | stdlib | Value parsing for `input <id> <value>` | Parse user-provided values to correct types before setting Future result |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.Future` | `asyncio.Event` + value slot | Event is boolean; Future carries typed result. Future is cleaner for single-value resolution. |
| `Gate` marker | Dep function that awaits a bridge object | Dep-based approach requires injecting bridge objects; marker approach is declarative and matches existing `Dep`/`Recall` pattern. |
| Cross-mode `@gid` prefix | `!gid` prefix | `@` already used for NL session routing (`@2 hello`). Using `@g1 value` for gates requires disambiguation. `@g` prefix (always lowercase g + digits) is distinguishable from `@session_label`. |

## Architecture Patterns

### Recommended Module Structure
```
bae/
├── markers.py           # + Gate dataclass (sibling to Dep, Recall, Effect)
├── resolver.py          # + gate field classification + resolve_fields gate handling
├── repl/
│   ├── engine.py        # + WAITING state, InputGate registry, Future lifecycle
│   ├── graph_commands.py # + `input` command handler
│   ├── toolbar.py       # + pending gate badge widget
│   └── shell.py         # + cross-mode @gid routing in _dispatch()
```

### Pattern 1: Gate Marker on Node Fields

**What:** A `Gate` dataclass in `markers.py` that annotates node fields requiring human input. The resolver classifies these as `"gate"` (alongside `"dep"`, `"recall"`, `"plain"`).

**When to use:** Any node field that must be provided by the user mid-graph.

**Why this over a Dep function approach:** The Dep approach would require graph authors to write a dep function that receives an injected bridge, awaits it, and returns the value. The Gate marker is declarative -- the user annotates a field and the engine handles the suspension mechanics. This matches bae's philosophy: nodes are data frames, annotations drive behavior.

```python
# markers.py
@dataclass(frozen=True)
class Gate:
    """Marker for fields requiring human input during graph execution.

    Gate() suspends graph execution until the user provides a value.
    The field name, type, and description are displayed as a prompt.

    Usage:
        class DeployConfirm(Node):
            proceed: Annotated[bool, Gate(description="Deploy to prod?")]
    """
    description: str = ""
```

```python
# Node usage
class ConfirmAction(Node):
    user_approved: Annotated[bool, Gate(description="Approve this action?")]
    reason: str  # LLM fills this

    async def __call__(self) -> Execute | Abort: ...
```

### Pattern 2: InputGate as Future Wrapper with Schema

**What:** An `InputGate` dataclass in `engine.py` that wraps an `asyncio.Future` with schema metadata (field name, field type, description, graph run ID). The engine creates one per gate field encountered during `resolve_fields()`.

**When to use:** Engine-internal. Created when a gate-annotated field is encountered, destroyed when resolved.

```python
@dataclass
class InputGate:
    gate_id: str           # e.g. "g1.0" (run_id + sequential index)
    run_id: str            # which GraphRun this belongs to
    field_name: str        # Pydantic field name
    field_type: type       # target type for value coercion
    description: str       # from Gate marker or Field(description=...)
    future: asyncio.Future # the suspension primitive
    node_type: str         # which node class requested this gate
```

### Pattern 3: WAITING State in GraphState Enum

**What:** Add `WAITING = "waiting"` to `GraphState`. The engine transitions to WAITING when a gate field is encountered, and back to RUNNING when the gate is resolved.

**When to use:** Lifecycle tracking so `list` can show which graphs are waiting and what they're waiting for.

```python
class GraphState(enum.Enum):
    RUNNING = "running"
    WAITING = "waiting"   # new -- suspended at input gate
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

### Pattern 4: Gate Resolution via dep_cache Injection

**What:** The engine layer intercepts gate fields before `resolve_fields()` runs. For each gate field, it creates an `InputGate` (with Future), registers it in a pending gates registry, sets the Future into the dep_cache keyed by a gate sentinel, and lets `resolve_fields()` await it naturally through the existing dep resolution path.

**Critical insight:** The resolver already handles deps by looking up callables in `dep_cache` and awaiting them. A gate field's resolution can follow the same path -- the "dep function" is just `await future`, and the engine pre-creates and registers the Future in the cache.

**Alternative approach (simpler):** Instead of routing through the dep system, the engine wraps `resolve_fields()` to intercept gate-classified fields. Before calling the inner `resolve_fields()`, it creates Futures for any gate fields, registers them, transitions to WAITING, then awaits all gate Futures concurrently with `asyncio.gather()`. Once resolved, it passes the gate values alongside resolved deps/recalls into the node construction.

```python
# In engine._execute, wrapping the arun loop:
# The engine passes a custom resolve hook or wraps resolve_fields
# to handle gate fields before/alongside dep fields.
```

### Pattern 5: Cross-Mode Input Routing

**What:** The `@gid <value>` prefix is parsed in `_dispatch()` before mode-specific handling. `@g1 yes` resolves gate on graph run g1 regardless of current mode. The prefix `@g` followed by digits is distinguishable from NL session labels (which are arbitrary strings like `@2`, `@work`).

**Disambiguation rule:** `@g<digits>` where the character after `@` is literally `g` followed by one or more digits routes to graph input. All other `@` prefixes route to NL sessions.

```python
# In shell._dispatch(), before mode dispatch:
if text.startswith("@g") and len(text) > 2:
    rest = text[2:]  # after "@g"
    # Parse: digits = run_id suffix, space, value
    # e.g. "@g1 yes" -> run_id="g1", value="yes"
    ...
```

### Pattern 6: Shush Mode Toggle

**What:** A per-preference toggle controlling whether gate notifications appear inline (default) or only as a toolbar badge count. Stored as a simple boolean on `CortexShell` (or in `SessionStore` settings).

```python
# shell.py
self.shush_gates = False  # False = inline notification, True = badge only
```

### Anti-Patterns to Avoid

- **Modifying Graph.arun() for gate handling:** Gates are a cortex (engine layer) concern. `Graph.arun()` in `graph.py` must not know about gates. The engine wraps resolution, not the framework.
- **Blocking the event loop waiting for input:** The Future must be `await`ed, not polled. `asyncio.Future` handles this correctly -- the coroutine suspends and the event loop remains free for REPL interaction.
- **Creating gates at graph definition time:** Gates are created at execution time when the resolver encounters gate fields. The `Gate` marker is static metadata; the `InputGate` (with Future) is runtime.
- **Using asyncio.Event instead of Future:** Event is a boolean flag with no return value. Future carries a typed result. Since gate fields have types (bool, str, int, etc.), Future is the correct primitive.
- **Separate "input mode" or modal dialogs:** Gates should not force a mode switch. The toolbar badge + cross-mode shortcut means the user can respond from any mode without disruption.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Suspension primitive | Custom event/callback system | `asyncio.Future` | Stdlib. Single-value, type-safe, exception-propagating, cancel-aware. |
| Schema extraction | Custom field parser | `Pydantic FieldInfo` + `get_type_hints()` | Already used in `Graph._input_fields` and `_build_plain_model()`. Consistent API. |
| Value coercion | Manual type parsing | `Pydantic TypeAdapter.validate_python()` | Handles bool("yes"), int("42"), JSON parsing, etc. with full validation. |
| Toolbar badge | New widget system | `ToolbarConfig.add("gates", fn)` | Existing widget registry. New widget is a lambda querying pending gate count. |
| Command parsing | argparse/click | Split-on-space dispatch (existing pattern) | `dispatch_graph` already does this for run/list/cancel/inspect/trace. Add `input` handler. |

**Key insight:** Every component of input gates has an existing primitive. The work is wiring: Gate marker -> resolver classification -> engine Future creation -> shell routing -> toolbar display.

## Common Pitfalls

### Pitfall 1: Deadlock When Graph Awaits Gate But REPL Can't Process Input

**What goes wrong:** If the graph's `await future` blocks the event loop, the REPL can't read user input, creating a deadlock.
**Why it happens:** Only if the Future await somehow prevents the event loop from running prompt_toolkit's prompt_async().
**How to avoid:** `asyncio.Future.await` is non-blocking to the event loop by design -- it yields control. The graph coroutine suspends at the await, the event loop continues running prompt_toolkit, and when the user provides input, the Future is resolved from the REPL dispatch path. This is NOT a real risk with correct asyncio usage.
**Warning signs:** If you find yourself adding `await asyncio.sleep()` loops to "wait for input," something is architecturally wrong.

### Pitfall 2: Gate Future Not Set When Graph Is Cancelled

**What goes wrong:** User cancels a graph while it's waiting at a gate. The Future is never resolved. The InputGate entry lingers in the registry.
**How to avoid:** When a graph is cancelled (via `cancel` command or Ctrl-C), clean up all pending InputGates for that run. Cancel the Futures (which raises CancelledError in the awaiting coroutine, which propagates through `arun()` to the engine's exception handler).
**Warning signs:** Growing `pending_gates` count after graph cancellations.

### Pitfall 3: Cross-Mode Prefix Collision with NL Session Labels

**What goes wrong:** User types `@g1 hello` intending to talk to NL session "g1", but it gets routed to graph input.
**How to avoid:** The disambiguation rule must be unambiguous. `@g` + digits is a reserved prefix for graph gates. Document this. If a user has an NL session labeled "g1", they cannot use `@g1` from non-NL modes. In NL mode, `@g1 hello` could either be session routing or graph input -- NL mode should prefer session routing and require `input g1 hello` for gates (they'd switch to GRAPH mode anyway, or use the prefix from other modes).
**Warning signs:** Test both paths: `@g1 yes` from PY mode (should route to gate), `@g1 hello` from NL mode (should route to NL session).

### Pitfall 4: Type Coercion Surprises for Gate Values

**What goes wrong:** User types `input g1 yes` for a `bool` field. Raw string "yes" needs coercion to `True`. `input g1 42` for an `int` field.
**How to avoid:** Use Pydantic's `TypeAdapter.validate_python()` for coercion. Pydantic handles `"yes"` -> `True`, `"42"` -> `42`, `"3.14"` -> `3.14`, JSON strings for complex types.
**Warning signs:** FillError on gate values because raw strings weren't coerced to target types.

### Pitfall 5: Multiple Gate Fields on Same Node

**What goes wrong:** A node has two gate fields. Both need user input. Do they block sequentially or concurrently? Does the user provide them one at a time or together?
**How to avoid:** Resolve all gate fields for a node concurrently using `asyncio.gather()` on their Futures. Display all pending gates for the node. The user can provide values in any order. Each `input <gate_id> <value>` resolves one gate. When all gates for the node are resolved, execution continues.
**Warning signs:** Graph stuck at WAITING even though the user has provided one of two values.

### Pitfall 6: Resolver Classification Must Handle Gate Fields

**What goes wrong:** `classify_fields()` in `resolver.py` doesn't know about `Gate`. Gate-annotated fields get classified as "plain" and the LLM tries to fill them.
**How to avoid:** Extend `classify_fields()` to detect `Gate` markers and return `"gate"`. The LLM fill path (`_build_plain_model()`) must exclude gate fields just like it excludes dep and recall fields.
**Warning signs:** LLM tries to hallucinate a value for a gate field instead of waiting for user input.

## Code Examples

### Gate Marker Definition
```python
# bae/markers.py
@dataclass(frozen=True)
class Gate:
    """Marker for fields requiring human input during graph execution.

    Gate() suspends graph execution at resolve time. The engine creates
    an asyncio.Future, displays the field schema as a prompt, and waits
    for user input before continuing.

    Usage:
        class ConfirmDeploy(Node):
            approved: Annotated[bool, Gate(description="Deploy to production?")]
    """
    description: str = ""
```

### InputGate Runtime Object
```python
# bae/repl/engine.py
@dataclass
class InputGate:
    gate_id: str
    run_id: str
    field_name: str
    field_type: type
    description: str
    node_type: str
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())

    @property
    def schema_display(self) -> str:
        """Human-readable prompt: field_name: type (description)."""
        type_name = getattr(self.field_type, '__name__', str(self.field_type))
        if self.description:
            return f"{self.field_name}: {type_name} (\"{self.description}\")"
        return f"{self.field_name}: {type_name}"
```

### Resolver Classification Extension
```python
# In resolver.py classify_fields():
from bae.markers import Dep, Gate, Recall

for m in metadata:
    if isinstance(m, Dep):
        result[name] = "dep"
        classified = True
        break
    if isinstance(m, Recall):
        result[name] = "recall"
        classified = True
        break
    if isinstance(m, Gate):
        result[name] = "gate"
        classified = True
        break
```

### Engine Gate Handling (Sketch)
```python
# In engine._execute, before arun:
# Option A: Wrap resolve_fields to intercept gates
# Option B: Pre-scan each node's gate fields, create Futures, inject via dep_cache

# Option B sketch:
async def _execute_with_gates(self, run, *, lm=None, **kwargs):
    # ... setup TimingLM, dep_cache ...

    # Override resolve_fields behavior for gate fields:
    # The arun loop calls resolve_fields per node.
    # We need to intercept gate fields before they reach normal resolution.

    # Approach: Provide a gate-aware LM wrapper or monkey-patch resolve_fields
    # through dep_cache. Better: use a GateAwareLM that also handles gate
    # field resolution at the engine level.

    # Simplest correct approach:
    # 1. Subclass or wrap the graph's arun to intercept per-node resolution
    # 2. For each node, classify fields. If gate fields exist:
    #    a. Create InputGates with Futures
    #    b. Register them in self._pending_gates
    #    c. Transition run to WAITING
    #    d. Emit notification
    #    e. await asyncio.gather(*[gate.future for gate in node_gates])
    #    f. Transition run back to RUNNING
    #    g. Include resolved gate values in the node construction
```

### GRAPH Mode Input Command
```python
# In graph_commands.py:
async def _cmd_input(arg: str, shell) -> None:
    """Resolve a pending input gate: input <gate_id> <value>."""
    parts = arg.strip().split(None, 1)
    if len(parts) < 2:
        shell.router.write("graph", "usage: input <id> <value>", mode="GRAPH")
        return

    gate_id, raw_value = parts
    gate = shell.engine.get_pending_gate(gate_id)
    if gate is None:
        shell.router.write("graph", f"no pending gate {gate_id}", mode="GRAPH")
        return

    # Coerce value to target type
    from pydantic import TypeAdapter
    try:
        adapter = TypeAdapter(gate.field_type)
        value = adapter.validate_python(raw_value)
    except Exception as e:
        shell.router.write(
            "graph",
            f"invalid value for {gate.field_name} ({gate.field_type.__name__}): {e}",
            mode="GRAPH",
        )
        return

    gate.future.set_result(value)
    shell.router.write(
        "graph", f"resolved {gate_id}: {gate.field_name} = {value!r}",
        mode="GRAPH",
        metadata={"type": "lifecycle", "run_id": gate.run_id},
    )
```

### Cross-Mode Routing
```python
# In shell._dispatch(), before mode-specific dispatch:
async def _dispatch(self, text: str) -> None:
    # Cross-mode gate input: @g<digits> <value>
    if text.startswith("@g") and len(text) > 2:
        rest = text[2:]
        space = rest.find(" ")
        if space > 0 and rest[:space].isdigit():
            gate_id = "g" + rest[:space]
            value = rest[space + 1:]
            # Delegate to gate resolution logic
            await self._resolve_gate(gate_id, value)
            return

    # ... existing mode dispatch ...
```

### Toolbar Badge Widget
```python
# In toolbar.py:
def make_gates_widget(shell) -> ToolbarWidget:
    """Built-in widget: pending input gate count (hidden when zero)."""
    def widget():
        n = shell.engine.pending_gate_count()
        if n == 0:
            return []
        label = f" {n} gate{'s' if n != 1 else ''} "
        return [("class:toolbar.gates", label)]
    return widget
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.Event` for pause/resume | `asyncio.Future` for typed suspension | Always available | Future carries result value; Event is boolean-only |
| LangGraph `interrupt()` + checkpointer | `asyncio.Future` in dep_cache (no persistence) | N/A (different system) | No checkpointing needed -- bae graphs are short-lived, in-process |
| Prefect `pause_flow_run(wait_for_input=Model)` | Gate marker + resolver integration | N/A (different system) | Same concept (Pydantic schema for input), simpler implementation |

**Deprecated/outdated:**
- None. `asyncio.Future` is the standard stdlib primitive and has not changed semantically.

## Open Questions

1. **Gate Resolution Granularity: Per-Field or Per-Node?**
   - What we know: The `input` command takes a gate_id which maps to a single field. Multiple gate fields on one node each get their own gate_id and their own Future.
   - What's unclear: Should the gate_id be `g1.0`, `g1.1` (run.field_index) or use the field name like `g1.approved`? Field names are more readable but could collide across nodes. Index-based is unambiguous.
   - Recommendation: Use `g<run_id>.<field_index>` (e.g., `g1.0`) for gate_id. Show field name in schema display. The `input` command shows pending gates with their IDs and descriptions, so the user knows what each ID means.

2. **How Does the Engine Intercept Gate Fields in arun()?**
   - What we know: `Graph.arun()` calls `resolve_fields()` per node, which reads dep_cache. The engine provides dep_cache. Gate fields need to be awaited during resolution.
   - What's unclear: The cleanest integration point. Options: (A) Extend `resolve_fields()` to handle gate-classified fields by awaiting Futures from dep_cache. (B) Wrap `arun()` to intercept per-node resolution. (C) Use a custom LM wrapper that also handles gate resolution.
   - Recommendation: **Option A** -- extend `resolve_fields()` in `resolver.py`. It already handles dep and recall fields. Adding gate field handling (lookup Future in dep_cache, await it) is a natural extension. The engine pre-creates Futures and injects them into dep_cache keyed by `(Gate, field_name, node_cls)` or a sentinel. This keeps the engine's role to "create Futures + inject" and the resolver's role to "await + return value."

3. **NL Mode `@g1` Conflict**
   - What we know: In NL mode, `@label message` switches AI session. `@g1 hello` would be ambiguous -- NL session "g1" or graph gate "g1"?
   - What's unclear: Should NL mode prioritize session routing or graph gates when prefix matches `@g<digits>`?
   - Recommendation: In NL mode, `@g1` routes to NL session (existing behavior wins). From non-NL modes (PY, BASH), `@g1` routes to graph gates. In GRAPH mode, use `input g1 <value>` directly. This means NL mode users who need to resolve a gate must switch to GRAPH mode or use PY/BASH mode. This is acceptable because gate resolution is an explicit action, not a conversational one.

4. **Shush Mode Persistence**
   - What we know: Shush mode toggles between inline notification and badge-only.
   - What's unclear: Should this be stored in SessionStore for persistence across sessions?
   - Recommendation: Start as a simple boolean on CortexShell. Persist later if users want it. YAGNI for now.

## Sources

### Primary (HIGH confidence)
- `bae/resolver.py` -- classify_fields(), resolve_fields() implementation
- `bae/markers.py` -- Dep, Recall, Effect marker pattern
- `bae/repl/engine.py` -- GraphRegistry, GraphRun, GraphState, TimingLM
- `bae/repl/graph_commands.py` -- dispatch_graph(), existing command handlers
- `bae/repl/toolbar.py` -- ToolbarConfig, widget factories
- `bae/repl/shell.py` -- _dispatch(), cross-mode routing, @prefix parsing
- `bae/graph.py` -- Graph.arun() execution loop, dep_cache parameter
- `bae/lm.py` -- _build_plain_model() excludes non-plain fields
- Python docs: [asyncio.Future](https://docs.python.org/3/library/asyncio-future.html) -- Future API

### Secondary (MEDIUM confidence)
- `.planning/research/FEATURES.md` -- Feature landscape research (InputBridge pattern)
- `.planning/phases/26-engine-foundation/26-RESEARCH.md` -- WAITING state design notes
- `.planning/STATE.md` -- Phase 28 flagged research notes, deadlock pitfall
- LangGraph interrupt pattern -- WebSearch verified against official docs
- Prefect pause_flow_run pattern -- WebSearch verified against official docs

### Tertiary (LOW confidence)
- None. All findings verified against codebase or official documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib/existing deps, no new libraries
- Architecture: HIGH -- markers/resolver/engine pattern proven by Dep/Recall/Effect, extending same pattern
- Pitfalls: HIGH -- asyncio Future semantics well-understood, deadlock prevention verified against event loop model
- Cross-mode routing: MEDIUM -- `@g` prefix disambiguation needs testing, NL mode conflict needs explicit decision

**Research date:** 2026-02-15
**Valid until:** 2026-03-15 (stable -- no external dependencies to drift)
