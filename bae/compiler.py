"""DSPy compiler for graph optimization.

Compiles a Graph into a DSPy program for prompt optimization.
"""

from typing import Annotated, Any, get_args, get_origin, get_type_hints

import dspy

from bae.graph import Graph
from bae.markers import Context
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


def node_to_signature(node_cls: type[Node]) -> type[dspy.Signature]:
    """Convert a Node class to a DSPy Signature.

    - Class name becomes instruction text
    - Annotated[type, Context(description="...")] fields become InputFields
    - Unannotated fields are excluded (internal state)
    - Return type becomes OutputField (str for Phase 1)

    Args:
        node_cls: The node class to convert.

    Returns:
        A dspy.Signature subclass with the appropriate fields.
    """
    fields: dict[str, tuple[type, dspy.InputField | dspy.OutputField]] = {}

    # Extract annotated fields using include_extras=True to preserve Annotated wrapper
    hints = get_type_hints(node_cls, include_extras=True)
    for name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            base_type = args[0]
            metadata = args[1:]

            # Look for our Context marker in the metadata
            for meta in metadata:
                if isinstance(meta, Context):
                    fields[name] = (base_type, dspy.InputField(desc=meta.description))
                    break

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
