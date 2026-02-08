"""Field resolver for Dep and Recall annotations.

Inspects Node subclass type hints to classify each field as 'dep' (populated
by a callable), 'recall' (populated from the execution trace), or 'plain'
(supplied directly by the caller or LLM).
"""

from __future__ import annotations

import graphlib
from typing import Annotated, get_args, get_origin, get_type_hints

from bae.exceptions import RecallError
from bae.markers import Dep, Recall


def classify_fields(node_cls: type) -> dict[str, str]:
    """Classify each field of a Node subclass by its annotation marker.

    Inspects ``typing.Annotated`` metadata for ``Dep`` or ``Recall`` markers.
    Fields without a recognized marker are classified as ``"plain"``.

    Args:
        node_cls: A Node subclass whose fields to classify.

    Returns:
        Dict mapping field name to ``"dep"``, ``"recall"``, or ``"plain"``.
    """
    hints = get_type_hints(node_cls, include_extras=True)
    result: dict[str, str] = {}

    for name, hint in hints.items():
        if name == "return":
            continue

        if get_origin(hint) is Annotated:
            metadata = get_args(hint)[1:]
            classified = False
            for m in metadata:
                if isinstance(m, Dep):
                    result[name] = "dep"
                    classified = True
                    break
                if isinstance(m, Recall):
                    result[name] = "recall"
                    classified = True
                    break
            if not classified:
                result[name] = "plain"
        else:
            result[name] = "plain"

    return result


def recall_from_trace(trace: list, target_type: type) -> object:
    """Search the execution trace backward for a field matching the target type.

    Walks ``reversed(trace)`` so the most recently executed node wins. Only
    LLM-filled (plain) fields are searched -- fields annotated with ``Dep`` or
    ``Recall`` are infrastructure and skipped.

    Args:
        trace: List of executed Node instances (oldest first).
        target_type: The type to match against field annotations.

    Returns:
        The value of the first matching field found (most recent node first).

    Raises:
        RecallError: If no matching field is found in the entire trace.
    """
    for node in reversed(trace):
        hints = get_type_hints(node.__class__, include_extras=True)
        for field_name, hint in hints.items():
            if field_name == "return":
                continue

            # Determine if this field is infrastructure (Dep or Recall annotated)
            base_type = hint
            if get_origin(hint) is Annotated:
                args = get_args(hint)
                base_type = args[0]
                metadata = args[1:]
                if any(isinstance(m, (Dep, Recall)) for m in metadata):
                    continue

            # Check type match: field type must be a subclass of target type
            if isinstance(base_type, type) and issubclass(base_type, target_type):
                value = getattr(node, field_name, None)
                if value is not None:
                    return value

    raise RecallError(
        f"No field matching {target_type.__name__} found in trace"
    )


def _callable_name(fn: object) -> str:
    """Return a human-readable name for a callable."""
    return getattr(fn, "__qualname__", None) or getattr(fn, "__name__", repr(fn))


def build_dep_dag(node_cls: type) -> graphlib.TopologicalSorter:
    """Construct a TopologicalSorter from Dep-annotated fields and transitive deps.

    Walks ``node_cls`` fields for ``Dep`` markers, then recursively walks each
    dep function's parameters for nested ``Dep`` annotations (transitive deps).

    Args:
        node_cls: A Node subclass whose dep fields to walk.

    Returns:
        A ``graphlib.TopologicalSorter`` ready for ``static_order()`` or
        ``prepare()``.  Cycle detection happens when the caller iterates.
    """
    ts = graphlib.TopologicalSorter()
    visited: set = set()

    def walk(fn: object) -> None:
        if id(fn) in visited:
            return
        visited.add(id(fn))

        # Ensure leaf nodes appear in the DAG even with no deps
        ts.add(fn)

        try:
            hints = get_type_hints(fn, include_extras=True)
        except Exception:
            return

        for param_name, hint in hints.items():
            if param_name == "return":
                continue
            if get_origin(hint) is Annotated:
                for m in get_args(hint)[1:]:
                    if isinstance(m, Dep) and m.fn is not None:
                        ts.add(fn, m.fn)  # fn depends on m.fn
                        walk(m.fn)
                        break

    # Seed the DAG from node class fields
    hints = get_type_hints(node_cls, include_extras=True)
    for field_name, hint in hints.items():
        if field_name == "return":
            continue
        if get_origin(hint) is Annotated:
            for m in get_args(hint)[1:]:
                if isinstance(m, Dep) and m.fn is not None:
                    walk(m.fn)
                    break

    return ts


def validate_node_deps(node_cls: type, *, is_start: bool) -> list[str]:
    """Validate dep and recall annotations on a Node subclass at build time.

    Checks performed:
    - Circular dependency detection (via ``build_dep_dag`` + ``static_order``)
    - Dep function missing return type annotation
    - Dep function return type not assignable to the field type (MRO check)
    - Recall on a start node (no trace to search)

    Args:
        node_cls: A Node subclass to validate.
        is_start: Whether this node is the graph entry point.

    Returns:
        List of human-readable error strings. Empty list means valid.
    """
    errors: list[str] = []
    hints = get_type_hints(node_cls, include_extras=True)

    for field_name, hint in hints.items():
        if field_name == "return":
            continue

        if get_origin(hint) is not Annotated:
            continue

        base_type = get_args(hint)[0]
        metadata = get_args(hint)[1:]

        for m in metadata:
            if isinstance(m, Recall) and is_start:
                errors.append(
                    f"Recall() on field '{field_name}' of start node "
                    f"{node_cls.__name__}: no execution trace to search"
                )
            elif isinstance(m, Dep) and m.fn is not None:
                fn_name = _callable_name(m.fn)
                try:
                    dep_hints = get_type_hints(m.fn, include_extras=True)
                except Exception:
                    dep_hints = {}
                ret_type = dep_hints.get("return")
                if ret_type is None:
                    errors.append(
                        f"Dep function {fn_name} has no return type annotation"
                    )
                elif (
                    isinstance(ret_type, type)
                    and isinstance(base_type, type)
                    and not issubclass(ret_type, base_type)
                ):
                    errors.append(
                        f"Dep function {fn_name} returns {ret_type.__name__} "
                        f"but field '{field_name}' expects {base_type.__name__}"
                    )
            # Only process first marker per field
            break

    # Cycle detection
    try:
        dag = build_dep_dag(node_cls)
        list(dag.static_order())
    except graphlib.CycleError as e:
        cycle = e.args[1] if len(e.args) > 1 else []
        names = [_callable_name(fn) for fn in cycle]
        errors.append(f"Circular dependency detected: {' -> '.join(names)}")

    return errors


def resolve_dep(fn: object, cache: dict) -> object:
    """Resolve a single dep function, recursively resolving transitive deps.

    If ``fn`` is already in ``cache``, returns the cached value immediately.
    Otherwise, inspects ``fn``'s type hints for ``Dep``-annotated parameters,
    recursively resolves those first, then calls ``fn`` with the resolved kwargs.
    The result is stored in ``cache`` before returning.

    Exceptions from dep functions propagate raw (no wrapping).

    Args:
        fn: The dep callable to invoke.
        cache: Per-run cache dict keyed by callable identity.

    Returns:
        The result of calling fn with its resolved dep kwargs.
    """
    if fn in cache:
        return cache[fn]

    hints = get_type_hints(fn, include_extras=True)
    kwargs: dict[str, object] = {}

    for param_name, hint in hints.items():
        if param_name == "return":
            continue
        if get_origin(hint) is Annotated:
            for m in get_args(hint)[1:]:
                if isinstance(m, Dep) and m.fn is not None:
                    kwargs[param_name] = resolve_dep(m.fn, cache)
                    break

    result = fn(**kwargs)
    cache[fn] = result
    return result


def resolve_fields(node_cls: type, trace: list, dep_cache: dict) -> dict[str, object]:
    """Resolve all Dep and Recall fields on a Node subclass.

    Iterates fields in declaration order. For each ``Dep``-annotated field,
    delegates to :func:`resolve_dep`. For each ``Recall``-annotated field,
    delegates to :func:`recall_from_trace`. Plain fields are skipped.

    Args:
        node_cls: A Node subclass whose annotated fields to resolve.
        trace: Execution trace for Recall resolution.
        dep_cache: Per-run dep cache shared across resolve_fields calls.

    Returns:
        Dict mapping field name to resolved value for Dep and Recall fields only.
    """
    resolved: dict[str, object] = {}
    hints = get_type_hints(node_cls, include_extras=True)

    for field_name, hint in hints.items():
        if field_name == "return":
            continue

        if get_origin(hint) is not Annotated:
            continue

        args = get_args(hint)
        base_type = args[0]
        metadata = args[1:]

        for m in metadata:
            if isinstance(m, Dep) and m.fn is not None:
                resolved[field_name] = resolve_dep(m.fn, dep_cache)
                break
            if isinstance(m, Recall):
                resolved[field_name] = recall_from_trace(trace, base_type)
                break

    return resolved
