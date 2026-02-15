# Fix Options Analysis

## Problem
REPL-defined classes with `__module__='<cortex>'` fail when `get_type_hints()` is called without a `globalns` parameter, because Python cannot find the `<cortex>` module in `sys.modules`.

## Option 1: Local Fix in namespace.py (Minimal, REPL-specific)

**Approach:** Catch `NameError` in `_inspect_node_class()` and retry with the REPL namespace.

```python
def _inspect_node_class(self, node_cls: type[Node]):
    try:
        fields = classify_fields(node_cls)
    except NameError:
        # REPL-defined class - pass namespace to resolve annotations
        fields = self._classify_fields_with_ns(node_cls)

    # ... rest of method

def _classify_fields_with_ns(self, node_cls: type) -> dict[str, str]:
    """Like classify_fields but uses REPL namespace for annotation resolution."""
    hints = get_type_hints(node_cls, globalns=self._ns, include_extras=True)
    # ... rest of classify_fields logic
```

**Pros:**
- Minimal change, only touches namespace.py
- No impact on production code (resolver.py unchanged)
- REPL-specific problem gets REPL-specific fix

**Cons:**
- Code duplication (copy classify_fields logic)
- Only fixes `ns()` inspection - graph execution with REPL classes would still fail
- Incomplete fix - lm.py and compiler.py also call get_type_hints() directly

## Option 2: Pass globalns through resolver.py functions

**Approach:** Add optional `globalns` parameter to all resolver functions.

```python
def classify_fields(node_cls: type, globalns: dict | None = None) -> dict[str, str]:
    hints = get_type_hints(node_cls, globalns=globalns, include_extras=True)
    # ... rest
```

**Pros:**
- Systematic fix covering all use cases
- Allows REPL classes to work everywhere (ns, graph execution, etc.)
- Follows Python's typing.get_type_hints signature

**Cons:**
- Widespread changes across resolver.py (10+ get_type_hints calls)
- Every call site needs to pass globalns (namespace.py, lm.py, compiler.py, etc.)
- Adds complexity to production code for REPL edge case

## Option 3: Register <cortex> module in sys.modules

**Approach:** Make `<cortex>` a real module with the REPL namespace as its globals.

```python
# In repl/exec.py or namespace.py
import sys
import types

def _register_cortex_module(namespace: dict):
    if '<cortex>' not in sys.modules:
        cortex = types.ModuleType('<cortex>')
        cortex.__dict__.update(namespace)
        sys.modules['<cortex>'] = cortex
```

**Pros:**
- No changes to resolver.py
- REPL classes work everywhere automatically
- Clean: Python's module system is used as designed

**Cons:**
- Global state modification (sys.modules)
- Need to keep module dict in sync with REPL namespace
- Unusual pattern (fake module in sys.modules)

## Option 4: Fallback in get_type_hints wrapper

**Approach:** Wrap get_type_hints to auto-fallback to __annotations__ on NameError.

```python
def safe_get_type_hints(obj, **kwargs):
    try:
        return get_type_hints(obj, **kwargs)
    except NameError:
        # Fallback to raw annotations (no forward ref resolution)
        return obj.__annotations__
```

**Pros:**
- Minimal change to resolver.py (one wrapper function)
- Works everywhere

**Cons:**
- Loses annotation resolution (forward refs won't work)
- Silently degrades behavior instead of fixing root cause
- Incorrect for complex annotations

## Recommendation: Option 3 (Register <cortex> module)

**Why:**
1. **Complete fix:** REPL classes work everywhere (ns, graph creation, execution, lm.fill, compiler)
2. **No code changes to resolver/lm/compiler:** Zero production code impact
3. **Pythonic:** Uses Python's module system as designed
4. **Minimal implementation:** Single function, called once during REPL setup

**Implementation:**
```python
# In bae/repl/exec.py - register before first exec
def _ensure_cortex_module(namespace: dict):
    """Register <cortex> as a module so get_type_hints can resolve REPL classes."""
    import sys
    import types

    if '<cortex>' not in sys.modules:
        cortex = types.ModuleType('<cortex>')
        cortex.__dict__.update(namespace)
        sys.modules['<cortex>'] = cortex
    else:
        # Update existing module with latest namespace
        sys.modules['<cortex>'].__dict__.update(namespace)

# In async_exec(), before compile():
_ensure_cortex_module(namespace)
```

**Files to change:**
- `bae/repl/exec.py` - Add `_ensure_cortex_module()` function and call it in `async_exec()`

**Why not Option 1:**
- UAT test 5 says "ns(graph) shows topology" passed, implying graphs were created from REPL nodes
- graph.py line 72 calls get_type_hints() during graph creation - this would fail with Option 1
- lm.py and compiler.py also need to work with REPL classes
- Option 1 only fixes inspection, not execution

**Why not Option 2:**
- Threading globalns through 10+ functions across 4 files is complex
- Every call site needs updating (error-prone)
- Adds parameter clutter for a REPL-only edge case
