"""DSPy compiler for graph optimization.

Compiles a Graph into a DSPy program for prompt optimization.
"""

from __future__ import annotations

from typing import Annotated, Any, get_args, get_origin, get_type_hints

import dspy

from bae.graph import Graph
from bae.markers import Context, Dep
from bae.node import Node


class CompiledGraph:
    """A graph compiled to DSPy for optimization.

    The compiled graph can be:
    1. Run directly (uses DSPy modules for LLM calls)
    2. Optimized with DSPy optimizers (BootstrapFewShot, etc.)
    3. Saved/loaded for deployment
    """

    def __init__(self, graph: Graph, signatures: dict[type[Node], Any]):
        self.graph = graph
        self.signatures = signatures
        # TODO: DSPy modules for each node

    async def run(self, start_node: Node, **deps) -> Node | None:
        """Run the compiled graph."""
        # TODO: Use DSPy modules to produce next nodes
        raise NotImplementedError("DSPy compilation not yet implemented")

    def optimize(self, examples: list[tuple[Node, Node]], metric: Any) -> CompiledGraph:
        """Optimize the graph using DSPy."""
        # TODO: DSPy optimization
        raise NotImplementedError("DSPy optimization not yet implemented")


def _extract_context_fields(
    node_cls: type[Node],
) -> dict[str, tuple[type, dspy.InputField]]:
    """Extract Context-annotated class fields as InputFields."""
    fields: dict[str, tuple[type, dspy.InputField]] = {}

    hints = get_type_hints(node_cls, include_extras=True)
    for name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            base_type = args[0]
            metadata = args[1:]

            for meta in metadata:
                if isinstance(meta, Context):
                    fields[name] = (base_type, dspy.InputField(desc=meta.description))
                    break

    return fields


def _extract_dep_params(
    node_cls: type[Node],
) -> dict[str, tuple[type, dspy.InputField]]:
    """Extract Dep-annotated __call__ parameters as InputFields.

    Skips 'self', 'lm', and 'return' - only processes additional parameters.
    Only includes parameters with Annotated[type, Dep(...)] wrapper.
    """
    fields: dict[str, tuple[type, dspy.InputField]] = {}

    # Only process if node_cls defines its own __call__
    # (not inherited from Node base class)
    if "__call__" not in node_cls.__dict__:
        return fields

    try:
        call_hints = get_type_hints(node_cls.__call__, include_extras=True)
    except Exception:
        # If we can't get hints, return empty
        return fields

    # Skip these parameters
    skip_params = {"self", "lm", "return"}

    for name, hint in call_hints.items():
        if name in skip_params:
            continue

        if get_origin(hint) is Annotated:
            args = get_args(hint)
            base_type = args[0]
            metadata = args[1:]

            for meta in metadata:
                if isinstance(meta, Dep):
                    fields[name] = (base_type, dspy.InputField(desc=meta.description))
                    break

    return fields


def node_to_signature(node_cls: type[Node]) -> type[dspy.Signature]:
    """Convert a Node class to a DSPy Signature.

    - Class name becomes instruction text
    - Annotated[type, Context(description="...")] fields become InputFields
    - Annotated[type, Dep(description="...")] __call__ params become InputFields
    - Unannotated fields/params are excluded (internal state)
    - Return type becomes OutputField (str for Phase 1)

    Args:
        node_cls: The node class to convert.

    Returns:
        A dspy.Signature subclass with the appropriate fields.
    """
    fields: dict[str, tuple[type, dspy.InputField | dspy.OutputField]] = {}

    # Extract Context-annotated class fields
    fields.update(_extract_context_fields(node_cls))

    # Extract Dep-annotated __call__ parameters
    fields.update(_extract_dep_params(node_cls))

    # Output field (str for Phase 1 - union handling in Phase 2)
    fields["output"] = (str, dspy.OutputField())

    # Class name as instruction
    instruction = node_cls.__name__

    return dspy.make_signature(fields, instruction)


def compile_graph(graph: Graph) -> CompiledGraph:
    """Compile a Graph to DSPy.

    Args:
        graph: The graph to compile.

    Returns:
        CompiledGraph ready for execution or optimization.
    """
    signatures = {}

    for node_cls in graph.nodes:
        signatures[node_cls] = node_to_signature(node_cls)

    return CompiledGraph(graph, signatures)
