"""DSPy compiler for graph optimization.

Compiles a Graph into a DSPy program for prompt optimization.
"""

from typing import Any, get_type_hints

from bae.graph import Graph
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


def node_to_signature(node_cls: type[Node]) -> dict[str, Any]:
    """Convert a Node class to a DSPy-compatible signature definition.

    The signature represents:
    - Input: the node's fields (current state)
    - Output: the return type of __call__ (next node type(s))

    Args:
        node_cls: The node class to convert.

    Returns:
        Dict with node info and field definitions.
    """
    # Input = current node's fields
    fields = {}
    for name, field in node_cls.model_fields.items():
        fields[name] = {
            "type": field.annotation,
            "description": field.description or "",
            "required": field.is_required(),
        }

    # Output = return type hint (what node(s) __call__ can produce)
    hints = get_type_hints(node_cls.__call__)
    return_type = hints.get("return")

    return {
        "name": node_cls.__name__,
        "doc": node_cls.__doc__ or "",
        "fields": fields,
        "returns": return_type,
        "successors": node_cls.successors(),
        "is_terminal": node_cls.is_terminal(),
    }


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
