# Phase 1: Signature Generation - Research

**Researched:** 2026-02-04
**Domain:** DSPy Signature generation from Python class introspection
**Confidence:** HIGH

## Summary

This phase converts bae Node classes into valid DSPy Signature classes through automatic introspection. The core insight from DSPy documentation is that Signatures are Pydantic BaseModel subclasses with a custom metaclass that requires fields to be marked with `dspy.InputField()` or `dspy.OutputField()`. The `make_signature()` function provides the cleanest path for dynamic creation.

The locked decisions from CONTEXT.md simplify implementation significantly: class names are used as-is for instructions (no CamelCase parsing), and only `Annotated[type, Marker(description="...")]` fields become InputFields. Unannotated fields are internal state and excluded.

**Primary recommendation:** Use `dspy.make_signature()` with a dictionary of `{name: (type, FieldInfo)}` pairs, extracting field metadata from `typing.Annotated` annotations using `get_type_hints(include_extras=True)` and `get_args()`.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | >=2.0 | Signature generation, Predict modules | Already in pyproject.toml; official DSPy library |
| pydantic | >=2.0 | Field metadata, BaseModel | Already used by bae Node; DSPy built on Pydantic |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| typing (stdlib) | Python 3.14 | `get_type_hints`, `get_origin`, `get_args`, `Annotated` | For extracting field metadata |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `make_signature()` dict format | Subclassing `dspy.Signature` directly | Dict format is cleaner for dynamic creation at runtime |
| Custom marker class | `dspy.InputField` directly | Custom marker gives us domain-specific semantics (e.g., `Context`) while still compatible with DSPy |

**Installation:**
Already installed:
```bash
uv pip install dspy pydantic
```

## Architecture Patterns

### Recommended Project Structure
```
bae/
├── compiler.py     # node_to_signature() lives here (existing file)
├── markers.py      # Custom annotation markers (new file)
├── node.py         # Node base class (existing)
└── ...
```

### Pattern 1: Dynamic Signature Creation via make_signature()

**What:** Use DSPy's `make_signature()` with a dictionary mapping field names to `(type, FieldInfo)` tuples.

**When to use:** When creating Signatures dynamically from runtime introspection (our case).

**Example:**
```python
# Source: DSPy signature.py lines 519-602
from dspy import make_signature, InputField, OutputField

def node_to_signature(node_cls: type[Node]) -> type[dspy.Signature]:
    """Convert a Node class to a DSPy Signature."""
    fields = {}

    # Process annotated fields -> InputFields
    for name, annotation in get_annotated_fields(node_cls):
        base_type, description = extract_annotation_metadata(annotation)
        fields[name] = (base_type, InputField(desc=description))

    # Return type -> OutputField
    return_type = get_return_type(node_cls)
    fields["output"] = (return_type, OutputField())

    # Class name as instruction
    instruction = node_cls.__name__

    return make_signature(fields, instruction)
```

### Pattern 2: Extracting Annotated Metadata

**What:** Use `get_type_hints(include_extras=True)` to preserve `Annotated` wrappers, then `get_origin()` and `get_args()` to extract the base type and metadata.

**When to use:** When fields use `Annotated[type, Marker(description="...")]` pattern.

**Example:**
```python
# Source: Python typing docs
from typing import Annotated, get_type_hints, get_origin, get_args

def get_annotated_fields(cls) -> list[tuple[str, str, type]]:
    """Extract fields with Annotated markers."""
    hints = get_type_hints(cls, include_extras=True)
    results = []

    for name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            base_type = args[0]
            metadata = args[1:]  # tuple of metadata objects

            # Find our marker with description
            for meta in metadata:
                if hasattr(meta, 'description'):
                    results.append((name, base_type, meta.description))
                    break

    return results
```

### Pattern 3: Custom Annotation Marker

**What:** Define a simple dataclass or namedtuple as an annotation marker that carries the description.

**When to use:** When bae needs its own domain-specific marker (Claude's Discretion item).

**Example:**
```python
# bae/markers.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Context:
    """Marker for fields that should become DSPy InputFields."""
    description: str

# Usage in Node classes:
class AnalyzeUserIntent(Node):
    repl_log: Annotated[str, Context(description="The REPL's history.")]
```

### Anti-Patterns to Avoid

- **Subclassing Signature at runtime:** Don't use `type()` to create Signature subclasses directly. Use `make_signature()` which handles all the metaclass complexity.
- **Hardcoding field names:** Don't assume specific field names like "input" or "output". Extract from the actual Node class.
- **Ignoring Python 3.14 PEP 649:** DSPy already handles deferred annotation evaluation in its metaclass (lines 141-158 of signature.py). We should use `get_type_hints()` which also handles this correctly.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Signature class creation | Custom metaclass | `dspy.make_signature()` | DSPy's metaclass does extensive validation and setup (prefix inference, description defaults, etc.) |
| Field type inference | String parsing | `get_type_hints(include_extras=True)` | Handles forward refs, `__future__` imports, PEP 649 |
| Pydantic FieldInfo creation | Manual dict | `dspy.InputField()`, `dspy.OutputField()` | They use `pydantic.Field()` internally with correct `json_schema_extra` setup |
| CamelCase to Title Case | Regex | `dspy.signatures.signature.infer_prefix()` | Already exists in DSPy if needed later |

**Key insight:** DSPy's `make_signature()` function already handles all the edge cases of dynamic Signature creation. It accepts a dict of `{name: (type, FieldInfo)}` and returns a properly constructed Signature class.

## Common Pitfalls

### Pitfall 1: Forgetting include_extras=True

**What goes wrong:** `get_type_hints()` by default strips `Annotated` wrappers, returning just the base type.

**Why it happens:** Default behavior optimized for type checking, not runtime introspection.

**How to avoid:** Always use `get_type_hints(cls, include_extras=True)` when extracting annotation metadata.

**Warning signs:** All fields appear to have no metadata, even when `Annotated[type, marker]` is used.

### Pitfall 2: Missing __dspy_field_type Validation

**What goes wrong:** DSPy Signature metaclass rejects fields without `__dspy_field_type` in `json_schema_extra`.

**Why it happens:** Using `pydantic.Field()` directly instead of `dspy.InputField()` or `dspy.OutputField()`.

**How to avoid:** Always use DSPy's field factories, never raw Pydantic Field.

**Warning signs:** `TypeError: Field 'X' in 'Y' must be declared with InputField or OutputField`.

### Pitfall 3: Confusing Node Fields with Signature Fields

**What goes wrong:** Including all Node model_fields in the Signature, when only annotated fields should be inputs.

**Why it happens:** Using `node_cls.model_fields` instead of checking for our annotation marker.

**How to avoid:** Only fields with `Annotated[type, Context(...)]` (or similar marker) become InputFields. Unannotated fields are internal state.

**Warning signs:** Signature has too many input fields; internal state leaks to LLM prompt.

### Pitfall 4: Return Type is Not the Same as OutputField Type

**What goes wrong:** Trying to use `Node | OtherNode | None` union type as the OutputField annotation.

**Why it happens:** Confusing the return type hint (what `__call__` returns) with what the Signature should output.

**How to avoid:** For Phase 1, the OutputField should probably be a structured representation of what the LLM needs to decide/produce. The exact mapping from return type to OutputField is a design decision.

**Warning signs:** Complex union types in Signature output fields cause DSPy parsing issues.

## Code Examples

Verified patterns from official sources:

### Creating a Signature from Dict

```python
# Source: DSPy signature.py make_signature() function
import dspy

# Dictionary format: {name: (type, FieldInfo)}
fields = {
    "context": (str, dspy.InputField(desc="Background information")),
    "question": (str, dspy.InputField(desc="User's question")),
    "answer": (str, dspy.OutputField(desc="The response")),
}

MySignature = dspy.make_signature(fields, "Answer the question based on context")

# MySignature is now a proper dspy.Signature subclass
assert issubclass(MySignature, dspy.Signature)
assert MySignature.instructions == "Answer the question based on context"
assert "context" in MySignature.input_fields
assert "answer" in MySignature.output_fields
```

### Extracting Annotated Metadata

```python
# Source: Python typing module docs
from typing import Annotated, get_type_hints, get_origin, get_args
from dataclasses import dataclass

@dataclass(frozen=True)
class Context:
    description: str

class MyNode:
    repl_log: Annotated[str, Context(description="The REPL's history")]
    internal_state: int  # No Annotated - internal only

# Get hints with Annotated preserved
hints = get_type_hints(MyNode, include_extras=True)

for name, hint in hints.items():
    if get_origin(hint) is Annotated:
        args = get_args(hint)
        base_type = args[0]  # str
        metadata = args[1:]  # (Context(description="The REPL's history"),)

        for meta in metadata:
            if isinstance(meta, Context):
                print(f"{name}: {base_type}, desc={meta.description}")
                # Output: repl_log: <class 'str'>, desc=The REPL's history
```

### DSPy Field Internals

```python
# Source: DSPy field.py
import dspy
import pydantic

# InputField and OutputField are thin wrappers around pydantic.Field
input_field = dspy.InputField(desc="A description")

# The field stores DSPy-specific data in json_schema_extra
assert input_field.json_schema_extra["__dspy_field_type"] == "input"
assert input_field.json_schema_extra["desc"] == "A description"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| String-based signatures `"input -> output"` | Class-based or dict-based signatures | DSPy 2.x | Better type safety, IDE support |
| TypedPredictor for Pydantic | Regular Predict with Pydantic types | DSPy 2.x | Pydantic types work natively with Predict |
| Manual json_schema_extra | InputField/OutputField factories | DSPy 2.x | Cleaner API, less error-prone |

**Deprecated/outdated:**
- `dspy.functional.TypedPredictor`: Still works but regular `Predict` now handles Pydantic types natively

## Open Questions

Things that couldn't be fully resolved:

1. **OutputField type for union returns**
   - What we know: Node `__call__` returns `Node | OtherNode | None`. DSPy supports Pydantic types as outputs.
   - What's unclear: Should the OutputField type be the union? A string choice? A structured decision object?
   - Recommendation: For Phase 1, keep it simple. Either output a string choice ("Process" or "Clarify") or defer to Phase 2's two-step decide pattern.

2. **Handling nodes without any annotated fields**
   - What we know: User marked this as "Claude's Discretion"
   - What's unclear: Should we error, create a Signature with no inputs, or auto-generate a generic input?
   - Recommendation: Create a Signature with just the class name as instruction and the output field. No inputs is valid - it means "given nothing, decide what to output."

3. **Dep fields (typed deps like Request, TodoList)**
   - What we know: Requirements SIG-03 mentions dep fields should become InputFields
   - What's unclear: How are deps annotated differently from regular fields?
   - Recommendation: If deps use the same `Annotated[type, Marker]` pattern, they're handled identically. If they have a different marker, we'll need to recognize that marker type too.

## Sources

### Primary (HIGH confidence)
- DSPy source code `/Users/dzaramelcone/lab/bae/.venv/lib/python3.14/site-packages/dspy/signatures/signature.py` - make_signature() function, SignatureMeta metaclass
- DSPy source code `/Users/dzaramelcone/lab/bae/.venv/lib/python3.14/site-packages/dspy/signatures/field.py` - InputField(), OutputField() implementation
- [DSPy Signatures documentation](https://dspy.ai/learn/programming/signatures/) - Class-based signature patterns
- [Python typing documentation](https://docs.python.org/3/library/typing.html) - Annotated, get_type_hints, get_origin, get_args

### Secondary (MEDIUM confidence)
- [DSPy Signature API](https://dspy.ai/api/signatures/Signature/) - Class methods, dynamic creation
- [DSPy Cheatsheet](https://dspy.ai/cheatsheet/) - Core patterns
- [Create DSPy Signatures from Pydantic Models gist](https://gist.github.com/seanchatmangpt/7e25b66ebffdedba7310d9c90f377463) - Community pattern for dynamic creation

### Tertiary (LOW confidence)
- [TypedPredictorSignature PR](https://github.com/stanfordnlp/dspy/pull/1655) - Advanced Pydantic-to-Signature patterns (may be more complex than needed)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - DSPy source code directly examined
- Architecture: HIGH - `make_signature()` is documented and source-verified
- Pitfalls: HIGH - Derived from source code analysis of SignatureMeta.__new__

**Research date:** 2026-02-04
**Valid until:** 2026-03-04 (DSPy is actively developed but core Signature API is stable)
