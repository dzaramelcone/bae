# Phase 17: Namespace - Research

**Researched:** 2026-02-13
**Domain:** Pre-loaded REPL namespace with bae objects, expression result capture, and object introspection
**Confidence:** HIGH

## Summary

Phase 17 adds a reflective namespace to the cortex REPL. The namespace is the shared `dict` that `CortexShell` already owns (`self.namespace`), currently seeded with `asyncio`, `os`, `__builtins__`, `store`, and `channels`. This phase extends it with bae's core types (`Node`, `Graph`, `Dep`, `Recall`, etc.) so users can build graphs interactively without explicit imports. It also adds automatic result capture (`_` for expressions, `_trace` for graph runs) and a callable introspection function `ns()` that prints namespace contents or deep-inspects individual objects.

The `_` capture already works: `async_exec` in `exec.py` rewrites the last expression to `_ = <expr>` via AST transformation, storing the result in the namespace. The `_trace` capture requires a small change to `channel_arun` (or the GRAPH mode handler in `shell.py`) to store the trace list in the namespace after a successful `graph.arun()` call. The `ns()` function is a new callable placed in the namespace that dispatches on argument type: no args lists everything, a `Graph` argument shows topology, a `Node` subclass shows fields with annotations.

All introspection data is already available through existing Python and Pydantic APIs. `Graph` exposes `.nodes`, `.edges`, `.terminal_nodes`, `.start`. Node subclasses expose `.model_fields` (Pydantic field info), `get_type_hints(..., include_extras=True)` (Annotated metadata), `.successors()`, `.is_terminal()`. The `classify_fields()` function from `bae/resolver.py` categorizes fields as `dep`, `recall`, or `plain`. No new dependencies are needed.

**Primary recommendation:** Create `bae/repl/namespace.py` with (1) a `seed()` function that returns the initial namespace dict with all bae objects pre-loaded, and (2) a `NsInspector` callable class that implements `ns()` and `ns(obj)`. Wire `seed()` into `CortexShell.__init__`, replacing the inline dict. Wire `_trace` capture into the GRAPH mode handler after `channel_arun` returns.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `typing` (stdlib) | 3.14 | `get_type_hints(cls, include_extras=True)` for Annotated field introspection | Standard Python type introspection. Already used throughout bae. |
| `pydantic` | 2.x (installed) | `model_fields` dict for field names, annotations, metadata, defaults | Already the model system for Node. `FieldInfo` objects carry annotation metadata. |
| `bae.resolver.classify_fields` | internal | Categorize Node fields as `dep`/`recall`/`plain` | Already exists and tested. Reuse, don't reimplement. |
| `prompt_toolkit` | 3.0.52 (installed) | `print_formatted_text` + `FormattedText` for styled ns() output | Already the REPL output foundation from Phase 16. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `inspect` (stdlib) | 3.14 | `isclass()`, `isfunction()` for type dispatch in ns() | Distinguishing classes from instances from functions in ns(obj). |
| `textwrap` (stdlib) | 3.14 | `shorten()` for truncating long type repr in ns() listings | Keeping ns() output readable at terminal width. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom `NsInspector` class | Plain function `ns()` | A class with `__call__` gives a clean `repr()` when users type `ns` without parens. A plain function shows `<function ns at 0x...>` which is less helpful. |
| `print_formatted_text` for ns() output | Plain `print()` | `print()` works during `async_exec` stdout capture, meaning ns() output would be captured and displayed through the `[py]` channel correctly. `print_formatted_text` bypasses stdout capture. Use `print()` inside ns() so output flows through the standard channel path. |
| `classify_fields()` for field categorization | Manual Annotated introspection | `classify_fields` already handles all edge cases (ClassVar, nested Annotated). Reuse it. |

**Installation:**
```bash
# No new dependencies. All stdlib + existing bae internals.
```

## Architecture Patterns

### Recommended Project Structure

```
bae/repl/
    namespace.py    # NEW: seed(), NsInspector class
    shell.py        # Modified: uses seed() for namespace init, sets _trace after graph runs
    exec.py         # Unchanged: _ capture already works
    channels.py     # Unchanged
    store.py        # Unchanged
    complete.py     # Unchanged
    bash.py         # Unchanged
    modes.py        # Unchanged
```

### Pattern 1: Namespace Seeding

**What:** A `seed()` function returns the initial namespace dict with all bae objects pre-loaded. `CortexShell.__init__` calls it instead of building the dict inline.

**When to use:** Shell initialization.

```python
# bae/repl/namespace.py

import asyncio
import os

import bae


# Objects pre-loaded into the REPL namespace.
# Required by NS-01: Node, Graph, Dep, Recall.
# Additional useful types included for interactive use.
_PRELOADED = {
    # Core types (NS-01)
    "Node": bae.Node,
    "Graph": bae.Graph,
    "Dep": bae.Dep,
    "Recall": bae.Recall,
    # Useful extras for interactive graph building
    "GraphResult": bae.GraphResult,
    "LM": bae.LM,
    "NodeConfig": bae.NodeConfig,
    # Stdlib already in namespace (from Phase 14)
    "asyncio": asyncio,
    "os": os,
}


def seed() -> dict:
    """Build the initial REPL namespace with bae objects pre-loaded."""
    ns = {"__builtins__": __builtins__}
    ns.update(_PRELOADED)
    return ns
```

**Confidence:** HIGH -- straightforward dict construction. All objects verified accessible from `bae.__init__`.

### Pattern 2: NsInspector Callable Class

**What:** A class with `__call__` and `__repr__` placed in the namespace as `ns`. Calling `ns()` lists all objects. Calling `ns(obj)` deep-inspects. Typing `ns` without parens shows a helpful repr.

**When to use:** Placed in namespace during seed().

```python
class NsInspector:
    """Namespace introspection tool.

    ns()        -- list all namespace objects with types and summaries
    ns(graph)   -- show graph topology (nodes, edges)
    ns(MyNode)  -- show node fields with annotations
    ns(obj)     -- show type and attributes of any object
    """

    def __init__(self, namespace: dict) -> None:
        self._ns = namespace

    def __call__(self, obj=None):
        if obj is None:
            self._list_all()
        elif isinstance(obj, Graph):
            self._inspect_graph(obj)
        elif isinstance(obj, type) and issubclass(obj, Node):
            self._inspect_node_class(obj)
        elif isinstance(obj, Node):
            self._inspect_node_class(type(obj))
        else:
            self._inspect_generic(obj)

    def __repr__(self):
        return "ns() -- inspect namespace. ns(obj) -- inspect object."

    def _list_all(self):
        """Print all namespace objects with types and one-line summaries."""
        ...

    def _inspect_graph(self, graph):
        """Print graph topology: nodes, edges, terminals."""
        ...

    def _inspect_node_class(self, node_cls):
        """Print node fields with type, kind (dep/recall/plain), and annotations."""
        ...

    def _inspect_generic(self, obj):
        """Print type and key attributes of any object."""
        ...
```

**Confidence:** HIGH -- callable class pattern is standard Python. `isinstance` dispatch for Graph vs Node vs generic is straightforward.

### Pattern 3: Expression Result and Trace Capture

**What:** `_` is already captured by `async_exec`. `_trace` is set in the namespace after a graph run completes in GRAPH mode.

**When to use:** GRAPH mode handler in shell.py.

```python
# In shell.py GRAPH mode handler, after channel_arun returns:
result = await channel_arun(graph, text, self.router)
if result and result.trace:
    self.namespace["_trace"] = result.trace
```

**Confidence:** HIGH -- `channel_arun` already returns the `GraphResult`. Adding a namespace assignment is trivial.

### Pattern 4: ns() Output Formatting

**What:** `ns()` output uses plain `print()` to flow through the standard stdout capture path. This means output appears on the `[py]` channel with proper labeling. For `ns()` (list all), show a table-like format. For `ns(graph)`, show topology. For `ns(MyNode)`, show fields.

**When to use:** All ns() calls.

```python
# ns() output example:
# Name            Type          Summary
# ----            ----          -------
# Node            class         Base class for graph nodes
# Graph           class         Agent graph built from Node type hints
# Dep             class         Marker for dependency injection
# Recall          class         Marker for trace recall
# asyncio         module        async I/O support
# os              module        OS interface
# store           SessionStore  Session persistence (42 entries)
# channels        ChannelRouter 5 channels (4 visible)
# ns              NsInspector   ns() -- inspect namespace

# ns(graph) output example:
# Graph(start=IsTheUserGettingDressed)
#   Nodes: 5
#     IsTheUserGettingDressed -> AnticipateUsersDay, No
#     AnticipateUsersDay -> RecommendOOTD
#     No -> (terminal)
#     RecommendOOTD -> (terminal)
#   Terminals: No, RecommendOOTD

# ns(MyNode) output example:
# IsTheUserGettingDressed(Node)
#   Successors: AnticipateUsersDay | No
#   Terminal: no
#   Fields:
#     user_info     UserInfo  plain
#     user_message  str       plain
```

**Confidence:** HIGH -- all introspection data verified available via `Graph.nodes`, `Graph.edges`, `Node.model_fields`, `classify_fields()`, `Node.successors()`, `Node.is_terminal()`.

### Anti-Patterns to Avoid

- **Importing everything from bae into the namespace:** Pre-load only the types users need for interactive graph building. Don't dump `compile_graph`, `node_to_signature`, etc. into the namespace. Users can `from bae import X` for anything else.
- **Using `print_formatted_text` inside ns():** During `async_exec`, stdout is captured to a StringIO buffer. `print_formatted_text` writes directly to the terminal, bypassing capture. Use plain `print()` so ns() output flows through the standard `[py]` channel. Color formatting for ns() is a nice-to-have that can be added later if needed.
- **Making `_trace` a property or special object:** Keep it simple. `_trace` is a plain `list[Node]` stored in the namespace dict. Users can index it, iterate it, pass it to other functions. No wrapper objects.
- **Trying to prevent user reassignment of namespace builtins:** If a user does `Node = 42`, that's their choice. Don't guard against it. It violates the Python mental model.
- **Introspecting `__builtins__`:** Don't list every Python builtin in ns(). Skip keys starting with `_` in the listing. `__builtins__` is a dict with ~150 entries -- listing them all would drown the useful output.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Field classification (dep/recall/plain) | Custom Annotated parser | `bae.resolver.classify_fields()` | Already handles ClassVar, nested Annotated, edge cases. Tested. |
| Node field introspection | Walking `__annotations__` manually | `cls.model_fields` + `get_type_hints(cls, include_extras=True)` | Pydantic's `model_fields` gives `FieldInfo` with defaults, descriptions. `get_type_hints` gives full Annotated metadata. |
| Graph topology | Walking type hints manually | `graph.nodes`, `graph.edges`, `graph.terminal_nodes` | Graph already discovers and caches topology on `__init__`. |
| Node successor/terminal info | Parsing return types | `cls.successors()`, `cls.is_terminal()` | Already implemented on Node class. |
| String truncation | Manual slicing | `textwrap.shorten(s, width=N)` | Handles word boundaries, adds ellipsis. |

**Key insight:** All introspection data is already computed and cached by existing bae infrastructure. `ns()` is a presentation layer over `Graph.edges`, `Node.model_fields`, `classify_fields()`, `Node.successors()`, and `Node.is_terminal()`. The implementation is glue code that formats existing data for terminal display.

## Common Pitfalls

### Pitfall 1: ns() Output Not Appearing on [py] Channel

**What goes wrong:** ns() output shows in the terminal but doesn't appear as `[py]` channel output, or appears twice (once raw, once through channel).

**Why it happens:** `async_exec` captures `sys.stdout` to a StringIO buffer during execution. If ns() uses `print()`, output is captured correctly and routed through the `[py]` channel by shell.py. If ns() uses `print_formatted_text()`, it bypasses the capture and goes directly to the terminal.

**How to avoid:** Use plain `print()` inside ns() methods. The output will be captured by `async_exec`'s stdout redirect and then routed through `router.write("py", captured, ...)` in shell.py. This is the correct path.

**Warning signs:** ns() output appearing without `[py]` prefix, or appearing twice.

### Pitfall 2: _ Overwritten by ns() Return Value

**What goes wrong:** After calling `ns()`, `_` is set to `None` (the return value of ns()), overwriting the user's previous expression result.

**Why it happens:** `async_exec` captures the last expression's value in `_`. `ns()` is an expression that returns None, so `_ = None` after calling it.

**How to avoid:** This is actually the correct Python REPL behavior -- `_` always holds the last expression result. The CPython REPL works the same way. However, for ns(), since it has no useful return value, `__call__` should still return None. If users want to preserve `_`, they can assign to a named variable first. Document this behavior.

**Warning signs:** None -- this is expected Python behavior.

### Pitfall 3: Node Instance vs Node Class Confusion

**What goes wrong:** User calls `ns(my_node_instance)` expecting field values but gets the class introspection.

**Why it happens:** Both `isinstance(obj, Node)` and `isinstance(obj, type) and issubclass(obj, Node)` need to be handled.

**How to avoid:** Dispatch on both: if it's a Node subclass (type), show class fields. If it's a Node instance, also show class fields (same view). For instances, optionally show current field values too. The dispatch order matters: check `isinstance(obj, type)` before `isinstance(obj, Node)` because classes are not instances of themselves, but instances are instances of Node.

**Warning signs:** TypeError on `issubclass()` when passed a non-type.

### Pitfall 4: Circular Import from namespace.py

**What goes wrong:** `bae/repl/namespace.py` imports from `bae` (for Node, Graph, etc.) which imports from `bae/repl/` -- circular import.

**Why it happens:** `bae/__init__.py` does not import from `bae/repl/`. The repl package is a consumer of bae, not imported by it. So the import direction is one-way: `bae.repl.namespace -> bae` (safe).

**How to avoid:** Keep the import direction clean. `namespace.py` imports from `bae` at module level. `bae/__init__.py` never imports from `bae.repl`. This is already the established pattern (shell.py imports from bae, not vice versa).

**Warning signs:** `ImportError: cannot import name 'X' from partially initialized module`.

### Pitfall 5: _trace Not Set When Graph Errors

**What goes wrong:** If `channel_arun` raises an exception (e.g., max iterations exceeded), `_trace` is not updated. User has no way to inspect what happened.

**Why it happens:** The exception propagates before the namespace assignment.

**How to avoid:** Wrap the `_trace` assignment in a try/finally or catch the exception, set `_trace` to the partial trace from the exception (bae errors carry `.trace`), then re-raise. The `BaeError` and `DepError` classes already attach `.trace` to the exception object.

**Warning signs:** `_trace` is stale or empty after a failed graph run.

## Code Examples

### Namespace Seeding (NS-01)

```python
# bae/repl/namespace.py
import asyncio
import os

import bae


_PRELOADED = {
    "Node": bae.Node,
    "Graph": bae.Graph,
    "Dep": bae.Dep,
    "Recall": bae.Recall,
    "GraphResult": bae.GraphResult,
    "LM": bae.LM,
    "NodeConfig": bae.NodeConfig,
    "asyncio": asyncio,
    "os": os,
}


def seed() -> dict:
    """Build the initial REPL namespace with bae objects pre-loaded."""
    ns = {"__builtins__": __builtins__}
    ns.update(_PRELOADED)
    return ns
```

### NsInspector: List All (NS-03)

```python
def _list_all(self):
    """Print all namespace objects with types and one-line summaries."""
    items = []
    for name, obj in sorted(self._ns.items()):
        if name.startswith("_"):
            continue
        type_name = type(obj).__name__
        # Special cases for cleaner display
        if isinstance(obj, type):
            type_name = "class"
        elif callable(obj) and not isinstance(obj, type):
            type_name = "callable"
        summary = _one_liner(obj)
        items.append((name, type_name, summary))

    if not items:
        print("(namespace is empty)")
        return

    # Column-aligned output
    max_name = max(len(i[0]) for i in items)
    max_type = max(len(i[1]) for i in items)
    for name, type_name, summary in items:
        print(f"  {name:<{max_name}}  {type_name:<{max_type}}  {summary}")
```

### NsInspector: Inspect Graph (NS-04)

```python
def _inspect_graph(self, graph):
    """Print graph topology: start node, all nodes, edges, terminals."""
    print(f"Graph(start={graph.start.__name__})")
    print(f"  Nodes: {len(graph.nodes)}")
    for node_cls in sorted(graph.nodes, key=lambda n: n.__name__):
        succs = graph.edges.get(node_cls, set())
        if succs:
            succ_str = ", ".join(sorted(s.__name__ for s in succs))
        else:
            succ_str = "(terminal)"
        print(f"    {node_cls.__name__} -> {succ_str}")
    terminals = graph.terminal_nodes
    if terminals:
        print(f"  Terminals: {', '.join(sorted(n.__name__ for n in terminals))}")
```

### NsInspector: Inspect Node (NS-04)

```python
def _inspect_node_class(self, node_cls):
    """Print node fields with type, kind (dep/recall/plain), and annotations."""
    from bae.resolver import classify_fields

    print(f"{node_cls.__name__}(Node)")
    if node_cls.__doc__:
        print(f"  {node_cls.__doc__.strip().splitlines()[0]}")

    succs = node_cls.successors()
    if succs:
        print(f"  Successors: {' | '.join(s.__name__ for s in succs)}")
    print(f"  Terminal: {'yes' if node_cls.is_terminal() else 'no'}")

    fields = classify_fields(node_cls)
    model_fields = node_cls.model_fields
    if model_fields:
        print(f"  Fields:")
        max_name = max(len(n) for n in model_fields)
        for name, finfo in model_fields.items():
            kind = fields.get(name, "plain")
            ann = finfo.annotation
            type_name = ann.__name__ if hasattr(ann, "__name__") else str(ann)
            marker = ""
            if kind == "dep":
                for m in finfo.metadata:
                    if isinstance(m, Dep):
                        fn_name = getattr(m.fn, "__name__", "auto") if m.fn else "auto"
                        marker = f"  Dep({fn_name})"
                        break
            elif kind == "recall":
                marker = "  Recall()"
            print(f"    {name:<{max_name}}  {type_name}  {kind}{marker}")
```

### _trace Capture (NS-02)

```python
# In shell.py, GRAPH mode handler:
elif self.mode == Mode.GRAPH:
    graph = self.namespace.get("graph")
    if graph:
        try:
            result = await channel_arun(graph, text, self.router)
        except Exception as exc:
            # Capture partial trace from bae errors
            trace = getattr(exc, "trace", None)
            if trace:
                self.namespace["_trace"] = trace
            raise
        if result and result.trace:
            self.namespace["_trace"] = result.trace
    else:
        stub = "(Graph mode stub) Not yet implemented."
        self.router.write("graph", stub, mode="GRAPH")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Inline namespace dict in `__init__` | `seed()` function in namespace.py | Phase 17 | Clean separation, easy to extend, testable |
| No introspection | `ns()` callable | Phase 17 | Users can discover what's available without external docs |
| Only `_` for expression results | `_` + `_trace` for graph traces | Phase 17 | REPL captures both expression and graph execution results |

**Deprecated/outdated:**
- Nothing deprecated. This is new functionality.

## Open Questions

1. **Which bae objects should be pre-loaded beyond the required four?**
   - What we know: NS-01 requires `Node`, `Graph`, `Dep`, `Recall`. Other useful objects include `GraphResult`, `LM`, `NodeConfig`, `Annotated` (from typing).
   - What's unclear: Whether pre-loading too many objects clutters the namespace.
   - Recommendation: Pre-load `Node`, `Graph`, `Dep`, `Recall`, `GraphResult`, `LM`, `NodeConfig`. These are the ones users need for interactive graph building. Skip compiler/optimizer functions -- users who need those can import explicitly. Also pre-load `Annotated` from typing since it's needed for `Dep()` and `Recall()` field annotations.

2. **Should ns() output be colored/styled?**
   - What we know: ns() runs inside `async_exec` which captures stdout. `print_formatted_text` would bypass capture.
   - What's unclear: Whether plain text output is sufficient or users will want colors.
   - Recommendation: Start with plain `print()`. Color can be added later by having ns() detect whether stdout is being captured (check `sys.stdout` type) and choosing the appropriate output method. YAGNI for now.

3. **Should ns(node_instance) show current field values?**
   - What we know: `ns(MyNode)` (class) shows field definitions. An instance has actual values.
   - What's unclear: Whether instance inspection should show values, or just redirect to class inspection.
   - Recommendation: Show current field values for instances. Use `pydantic_model.model_dump()` to get values. This is immediately useful for debugging graph execution.

4. **Should `_trace` be a list or a GraphResult?**
   - What we know: `GraphResult` wraps the trace list and provides `.result` property. The trace itself is `list[Node]`.
   - What's unclear: Whether users want the convenience of `.result` or the simplicity of a plain list.
   - Recommendation: Store `_trace` as the plain `list[Node]` (i.e., `result.trace`). This is what the success criteria specifies ("_trace holds the trace"). Store the full `GraphResult` as `_result` for users who want it. Or just store the trace -- users can always get the last element with `_trace[-1]`.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `bae/repl/shell.py` -- `CortexShell.__init__` namespace dict construction (line 73), GRAPH mode handler (lines 171-177), channel_arun wrapper (lines 186-206)
- Existing codebase: `bae/repl/exec.py` -- `async_exec` already captures `_` via AST rewrite (lines 24-32)
- Existing codebase: `bae/graph.py` -- `Graph.nodes`, `.edges`, `.terminal_nodes`, `.start` properties (lines 148-161)
- Existing codebase: `bae/node.py` -- `Node.successors()`, `.is_terminal()`, `model_fields` (lines 187-197)
- Existing codebase: `bae/resolver.py` -- `classify_fields()` returns `dict[str, str]` mapping field name to dep/recall/plain (lines 28-64)
- Existing codebase: `bae/__init__.py` -- all public exports verified accessible (lines 1-56)
- Existing codebase: `bae/markers.py` -- `Dep` and `Recall` dataclass markers with metadata (lines 13-41)
- Runtime verification: `Graph.edges` returns `dict[type[Node], set[type[Node]]]` -- verified with ootd example
- Runtime verification: `Node.model_fields` returns Pydantic `FieldInfo` with `.annotation`, `.metadata`, `.is_required()` -- verified
- Runtime verification: `classify_fields()` correctly categorizes dep/recall/plain fields -- verified with AnticipateUsersDay
- Runtime verification: `get_type_hints(cls, include_extras=True)` preserves Annotated metadata -- verified

### Secondary (MEDIUM confidence)
- Python documentation: `typing.get_type_hints()` with `include_extras=True` preserves Annotated metadata
- Pydantic documentation: `model_fields` dict, `FieldInfo` class attributes

### Tertiary (LOW confidence)
- None. All findings verified with primary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All stdlib + existing bae internals. No new dependencies.
- Architecture: HIGH -- namespace.py is a thin presentation layer over existing introspection APIs. All data access patterns verified at runtime.
- Pitfalls: HIGH -- stdout capture interaction understood from Phase 14/16 research. Import direction verified safe. Edge cases (error traces, instance vs class) identified.
- NS-02 (_/trace capture): HIGH -- `_` already works. `_trace` is a one-line namespace assignment after channel_arun.

**Research date:** 2026-02-13
**Valid until:** 2026-03-15 (stable internal APIs, unlikely to change)
