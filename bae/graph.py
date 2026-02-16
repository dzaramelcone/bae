"""Graph discovery and execution.

The Graph class discovers topology from Node type hints and handles execution.
"""

import asyncio
import inspect
import logging
import types
from collections import deque
from typing import Annotated, Any, get_args, get_origin, get_type_hints

from pydantic.fields import FieldInfo

from bae.exceptions import BaeError, DepError, RecallError
from bae.lm import LM
from bae.markers import Effect
from bae.node import Node, _has_ellipsis_body, _unwrap_annotated, _wants_lm
from bae.resolver import LM_KEY, _engine_dep_cache, classify_fields, resolve_fields, validate_node_deps
from bae.result import GraphResult

logger = logging.getLogger(__name__)


def _get_base_type(hint: Any) -> type:
    """Extract base type from Annotated or return hint as-is.

    For union types like `X | None`, returns the non-None type.
    """
    if get_origin(hint) is Annotated:
        hint = get_args(hint)[0]

    # Handle union types (X | None) - extract the non-None type
    if isinstance(hint, types.UnionType):
        args = get_args(hint)
        non_none_types = [arg for arg in args if arg is not type(None)]
        if len(non_none_types) == 1:
            return non_none_types[0]
        # Multiple non-None types - return first one (edge case)
        if non_none_types:
            return non_none_types[0]

    return hint


def _build_context(node: Node) -> dict[str, object]:
    """Build context dict from node fields for LM fill."""
    return {
        name: getattr(node, name)
        for name in node.__class__.model_fields
        if hasattr(node, name)
    }


def _build_instruction(target_type: type) -> str:
    """Build instruction string from class name."""
    return target_type.__name__


def _get_routing_strategy(
    node_cls: type[Node],
) -> tuple[str, ...] | tuple[str, type] | tuple[str, list[type]]:
    """Determine the routing strategy for a node class.

    Returns:
        - ("custom",) - node has custom __call__ logic
        - ("terminal",) - node has ellipsis body with pure None return
        - ("make", target_type) - node has ellipsis body with single return type
        - ("decide", types_list) - node has ellipsis body with union or optional return
    """
    # Check if node has custom logic (non-ellipsis body)
    if not _has_ellipsis_body(node_cls.__call__):
        return ("custom",)

    # Get return type hints
    hints = get_type_hints(node_cls.__call__)
    return_hint = hints.get("return")

    # Pure None return
    if return_hint is None or return_hint is type(None):
        return ("terminal",)

    # Unwrap top-level Annotated (e.g. Annotated[X, Effect(fn)])
    unwrapped = _unwrap_annotated(return_hint)

    # Handle union types (X | Y | None)
    if isinstance(unwrapped, types.UnionType):
        args = get_args(unwrapped)
        concrete_types = [
            _unwrap_annotated(arg)
            for arg in args
            if arg is not type(None) and _unwrap_annotated(arg) is not type(None)
        ]
        concrete_types = [a for a in concrete_types if isinstance(a, type)]
        is_optional = type(None) in args

        # No concrete types -> terminal
        if not concrete_types:
            return ("terminal",)

        # Single type, not optional -> make
        if len(concrete_types) == 1 and not is_optional:
            return ("make", concrete_types[0])

        # Multiple types or optional -> decide
        return ("decide", concrete_types)

    # Single type (not union)
    if isinstance(unwrapped, type):
        return ("make", unwrapped)

    return ("terminal",)


def _get_effects(return_hint, target_type: type) -> list:
    """Extract Effect callables for a target type from a return hint."""
    def _collect(hint):
        if get_origin(hint) is not Annotated:
            return []
        args = get_args(hint)
        base = args[0]
        if base is target_type or (isinstance(base, type) and issubclass(target_type, base)):
            return [meta.fn for meta in args[1:] if isinstance(meta, Effect)]
        return []

    # Single Annotated
    if get_origin(return_hint) is Annotated:
        return _collect(return_hint)

    # Union with Annotated members
    if isinstance(return_hint, types.UnionType):
        for arg in get_args(return_hint):
            found = _collect(arg)
            if found:
                return found

    return []


class Graph:
    """Agent graph built from Node type hints.

    Usage:
    ```python
    graph = Graph(start=AnalyzeRequest)

    # Sync API (most common)
    result = graph.run(request="Build a web scraper", lm=lm)

    # Async API (when already in an event loop)
    result = await graph.arun(request="Build a web scraper", lm=lm)
    ```

    The graph topology is discovered by walking return type hints from the start node.
    """

    def __init__(self, start: type[Node]):
        """Initialize the graph.

        Args:
            start: The starting node type.

        Raises:
            TypeError: If start is an instance instead of a class, or has
                Recall fields or invalid deps.
        """
        if not isinstance(start, type):
            raise TypeError(
                f"Graph(start=...) expects a Node class, got an instance of "
                f"{type(start).__name__}. Use Graph(start={type(start).__name__}) "
                f"instead of Graph(start={type(start).__name__}(...))"
            )
        self.start = start
        self._nodes: dict[type[Node], set[type[Node]]] = {}
        self._discover()
        self._validate_start()

    def _validate_start(self) -> None:
        """Validate start node and compute input field schema."""
        errors = validate_node_deps(self.start, is_start=True)
        if errors:
            raise TypeError(f"{self.start.__name__}: {'; '.join(errors)}")

        fields = classify_fields(self.start)
        model_fields = self.start.model_fields

        self._input_fields: dict[str, FieldInfo] = {}
        for name, kind in fields.items():
            if kind == "plain" and name in model_fields:
                fi = model_fields[name]
                if fi.is_required():
                    self._input_fields[name] = fi

    def _discover(self) -> None:
        """Discover all nodes reachable from start via type hints."""
        visited: set[type[Node]] = set()
        queue: deque[type[Node]] = deque([self.start])

        while queue:
            node_cls = queue.popleft()
            if node_cls in visited:
                continue
            visited.add(node_cls)

            successors = node_cls.successors()
            self._nodes[node_cls] = successors

            for successor in successors:
                if successor not in visited:
                    queue.append(successor)

    @property
    def nodes(self) -> set[type[Node]]:
        """All node types in the graph."""
        return set(self._nodes.keys())

    @property
    def edges(self) -> dict[type[Node], set[type[Node]]]:
        """Adjacency list: node type -> set of successor types."""
        return self._nodes.copy()

    @property
    def terminal_nodes(self) -> set[type[Node]]:
        """Node types that can terminate the graph."""
        return {n for n in self._nodes if n.is_terminal()}

    def validate(self) -> list[str]:
        """Validate graph structure. Returns list of warnings/errors."""
        issues = []

        # Check for nodes with no terminal path (would cause infinite loops)
        nodes_with_terminal_path = set()
        for node_cls in self._nodes:
            if node_cls.is_terminal():
                nodes_with_terminal_path.add(node_cls)

        # Propagate backwards: if a node can reach a terminal, it has a terminal path
        changed = True
        while changed:
            changed = False
            for node_cls, successors in self._nodes.items():
                if node_cls in nodes_with_terminal_path:
                    continue
                if any(s in nodes_with_terminal_path for s in successors):
                    nodes_with_terminal_path.add(node_cls)
                    changed = True

        for node_cls in self._nodes:
            if node_cls not in nodes_with_terminal_path:
                issues.append(
                    f"{node_cls.__name__} has no path to a terminal node "
                    f"(potential infinite loop)"
                )

        return issues

    def run(self, *, lm: LM | None = None, max_iters: int = 10, **kwargs) -> GraphResult:
        """Execute the graph synchronously.

        Convenience wrapper around arun(). Cannot be called from within
        a running event loop (raises RuntimeError).

        Args:
            lm: Language model backend for producing nodes.
            max_iters: Maximum iterations (0 = infinite). Default 10.
            **kwargs: Input fields for the start node.

        Returns:
            GraphResult with trace of visited nodes.

        Raises:
            TypeError: If required start node fields are missing.
            BaeError: If max_iters exceeded.
            DepError: If a dependency function fails.
            RecallError: If recall finds no matching field in trace.
        """
        return asyncio.run(self.arun(lm=lm, max_iters=max_iters, **kwargs))

    async def arun(
        self,
        *,
        lm: LM | None = None,
        max_iters: int = 10,
        dep_cache: dict | None = None,
        **kwargs,
    ) -> GraphResult:
        """Execute the graph asynchronously.

        Use when already in an event loop. For sync callers, use run().

        Args:
            lm: Language model backend for producing nodes.
            max_iters: Maximum iterations (0 = infinite). Default 10.
            dep_cache: Pre-seeded resolver cache entries. Keys are dep
                functions, values are their cached results. Entries bypass
                dep function calls entirely.
            **kwargs: Input fields for the start node.

        Returns:
            GraphResult with trace of visited nodes.

        Raises:
            TypeError: If required start node fields are missing.
            BaeError: If max_iters exceeded.
            DepError: If a dependency function fails.
            RecallError: If recall finds no matching field in trace.
        """
        missing = set(self._input_fields) - set(kwargs)
        if missing:
            raise TypeError(
                f"{self.start.__name__} requires: {', '.join(sorted(missing))}"
            )

        start_node = self.start.model_construct(
            _fields_set=set(kwargs.keys()), **kwargs
        )

        if lm is None:
            from bae.lm import ClaudeCLIBackend

            lm = ClaudeCLIBackend()

        trace: list[Node] = []
        cache: dict = {LM_KEY: lm}
        if dep_cache is not None:
            cache.update(dep_cache)
        engine_cache = _engine_dep_cache.get(None)
        if engine_cache is not None:
            for k, v in engine_cache.items():
                if k not in cache:
                    cache[k] = v
        current: Node | None = start_node
        iters = 0

        try:
            while current is not None:
                await asyncio.sleep(0)  # yield to event loop

                # Iteration guard
                if max_iters and iters >= max_iters:
                    err = BaeError(f"Graph execution exceeded {max_iters} iterations")
                    err.trace = trace
                    raise err

                # 1. Resolve deps and recalls
                try:
                    resolved = await resolve_fields(current.__class__, trace, cache)
                except RecallError:
                    raise  # Already correct type
                except Exception as e:
                    err = DepError(
                        f"{e} failed on {current.__class__.__name__}",
                        node_type=current.__class__,
                        cause=e,
                    )
                    err.trace = trace
                    raise err from e

                # 2. Set resolved values on self
                for field_name, value in resolved.items():
                    object.__setattr__(current, field_name, value)

                logger.debug(
                    "Resolved %d fields on %s",
                    len(resolved),
                    current.__class__.__name__,
                )

                # 3. Append to trace (after resolution, before __call__)
                trace.append(current)

                # 4. Determine routing and execute
                strategy = _get_routing_strategy(current.__class__)

                if strategy[0] == "terminal":
                    # Terminal node -- already in trace, exit
                    current = None
                elif strategy[0] == "custom":
                    # Custom __call__ logic
                    source_node = current
                    if _wants_lm(current.__class__.__call__):
                        current = await current(lm)
                    else:
                        current = await current()

                    # Fill required plain fields the caller didn't set
                    if current is not None:
                        model_fields = current.__class__.model_fields
                        plain = {
                            n for n, k in classify_fields(current.__class__).items()
                            if k == "plain" and n in model_fields
                        }
                        unfilled = {
                            n for n in plain
                            if n not in (current.model_fields_set or set())
                            and model_fields[n].is_required()
                        }
                        if unfilled:
                            target_resolved = await resolve_fields(
                                current.__class__, trace, cache
                            )
                            for name in plain & (current.model_fields_set or set()):
                                target_resolved[name] = getattr(current, name)
                            current = await lm.fill(
                                current.__class__, target_resolved,
                                _build_instruction(current.__class__),
                                source=source_node,
                            )

                    # Fire effects annotated on the return type hint
                    if current is not None:
                        source_cls = source_node.__class__
                        raw_hint = get_type_hints(
                            source_cls.__call__, include_extras=True
                        ).get("return")
                        if raw_hint:
                            for fn in _get_effects(raw_hint, current.__class__):
                                result = fn(current)
                                if asyncio.iscoroutine(result):
                                    await result
                else:
                    # Ellipsis body -- LM routing via v2 API
                    source_cls = current.__class__
                    if strategy[0] == "make":
                        target_type = strategy[1]
                    elif strategy[0] == "decide":
                        types_list = list(strategy[1])
                        context = _build_context(current)
                        target_type = await lm.choose_type(types_list, context)
                    else:
                        current = None
                        iters += 1
                        continue

                    # Resolve target's dep/recall fields before fill
                    target_resolved = await resolve_fields(target_type, trace, cache)
                    instruction = _build_instruction(target_type)
                    current = await lm.fill(
                        target_type, target_resolved, instruction, source=current
                    )

                    # Fire effects annotated on the return type hint
                    raw_hint = get_type_hints(
                        source_cls.__call__, include_extras=True
                    ).get("return")
                    for fn in _get_effects(raw_hint, target_type):
                        result = fn(current)
                        if asyncio.iscoroutine(result):
                            await result

                iters += 1
        except Exception as e:
            if not hasattr(e, "trace"):
                e.trace = trace
            raise

        return GraphResult(node=None, trace=trace)

    def to_mermaid(self) -> str:
        """Generate Mermaid diagram of the graph."""
        lines = ["graph TD"]

        for node_cls, successors in self._nodes.items():
            node_name = node_cls.__name__

            # Style terminal nodes differently
            if node_cls.is_terminal():
                if successors:
                    # Can be terminal but also has successors
                    lines.append(f"    {node_name}{{{{`{node_name}`}}}}")
                else:
                    # Pure terminal (no successors)
                    lines.append(f"    {node_name}(({node_name}))")

            for succ in successors:
                succ_name = succ.__name__
                lines.append(f"    {node_name} --> {succ_name}")

        return "\n".join(lines)


def graph(start: type[Node]):
    """Create a free-standing async callable from a node graph.

    Discovers topology from `start`, builds a typed signature from the
    start node's required plain fields. BaseModel fields are flattened
    so callers pass simple kwargs instead of constructing internal types.

    Usage::

        ootd = graph(start=IsTheUserGettingDressed)
        result = await ootd(name="Dzara", user_message="hi")
    """
    from pydantic import BaseModel
    from pydantic.fields import PydanticUndefined

    g = Graph(start=start)

    # Map which input fields need BaseModel reconstruction
    # _composites: {original_field_name: (ModelClass, [sub_field_names])}
    _composites: dict[str, tuple[type, list[str]]] = {}
    params = []

    for name, fi in g._input_fields.items():
        ann = fi.annotation
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            # Flatten this BaseModel's fields into the signature
            sub_fields = []
            for sub_name, sub_fi in ann.model_fields.items():
                default = (
                    sub_fi.default
                    if sub_fi.default is not PydanticUndefined
                    else inspect.Parameter.empty
                )
                params.append(inspect.Parameter(
                    sub_name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    annotation=sub_fi.annotation,
                    default=default,
                ))
                sub_fields.append(sub_name)
            _composites[name] = (ann, sub_fields)
        else:
            # Simple type -- keep as-is
            params.append(inspect.Parameter(
                name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                annotation=fi.annotation,
            ))

    params.append(inspect.Parameter("lm", kind=inspect.Parameter.KEYWORD_ONLY, default=None))
    params.append(inspect.Parameter("dep_cache", kind=inspect.Parameter.KEYWORD_ONLY, default=None))

    async def wrapper(*, lm=None, dep_cache=None, **kwargs):
        # Reconstruct BaseModel objects from flat kwargs
        arun_kwargs = {}
        for orig_name, (model_cls, sub_fields) in _composites.items():
            model_kwargs = {f: kwargs.pop(f) for f in sub_fields if f in kwargs}
            arun_kwargs[orig_name] = model_cls(**model_kwargs)
        arun_kwargs.update(kwargs)
        return await g.arun(lm=lm, dep_cache=dep_cache, **arun_kwargs)

    wrapper.__signature__ = inspect.Signature(params)
    wrapper.__name__ = start.__name__
    wrapper.__doc__ = f"Run {start.__name__} graph."
    wrapper._name = start.__name__

    return wrapper
