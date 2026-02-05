"""DSPy compiler for graph optimization.

Compiles a Graph into a DSPy program for prompt optimization.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
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
        self.optimized: dict[type[Node], dspy.Predict] = {}

    def run(self, start_node: Node, **deps) -> "GraphResult":
        """Run the compiled graph using optimized predictors.

        Creates an OptimizedLM from loaded predictors and delegates
        to Graph.run(). Nodes with optimized predictors use them;
        others fall back to naive prompts.

        Args:
            start_node: The initial node to start execution.
            **deps: External dependencies to inject.

        Returns:
            GraphResult with final node and execution trace.
        """
        from bae.optimized_lm import OptimizedLM
        from bae.result import GraphResult

        lm = OptimizedLM(optimized=self.optimized)
        return self.graph.run(start_node, lm=lm, **deps)

    def optimize(
        self,
        trainset: list[dspy.Example],
        metric: Callable | None = None,
    ) -> "CompiledGraph":
        """Optimize all node predictors with collected traces.

        Args:
            trainset: Training examples (from trace_to_examples).
            metric: Scoring function (defaults to node_transition_metric).

        Returns:
            Self for chaining.
        """
        # Lazy import to avoid circular import
        from bae.optimizer import optimize_node

        for node_cls in self.graph.nodes:
            self.optimized[node_cls] = optimize_node(node_cls, trainset, metric)
        return self

    def save(self, path: str | Path) -> None:
        """Save optimized predictors to directory."""
        # Lazy import to avoid circular import
        from bae.optimizer import save_optimized

        save_optimized(self.optimized, Path(path))

    @classmethod
    def load(cls, graph: "Graph", path: str | Path) -> "CompiledGraph":
        """Load optimized predictors from directory."""
        # Lazy import to avoid circular import
        from bae.optimizer import load_optimized

        compiled = compile_graph(graph)
        compiled.optimized = load_optimized(list(graph.nodes), Path(path))
        return compiled


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


def node_to_signature(node_cls: type[Node]) -> type[dspy.Signature]:
    """Convert a Node class to a DSPy Signature.

    - Class name becomes instruction text
    - Annotated[type, Context(description="...")] fields become InputFields
    - Unannotated fields are excluded (internal state)
    - Dep-annotated params are for runtime injection, not LLM context
    - Return type becomes OutputField (str for Phase 1)

    Args:
        node_cls: The node class to convert.

    Returns:
        A dspy.Signature subclass with the appropriate fields.
    """
    fields: dict[str, tuple[type, dspy.InputField | dspy.OutputField]] = {}

    # Extract Context-annotated class fields
    fields.update(_extract_context_fields(node_cls))

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


def create_optimized_lm(
    graph: Graph,
    compiled_path: str | Path,
) -> "OptimizedLM":
    """Create an OptimizedLM with loaded predictors for a graph.

    Convenience factory that loads optimized predictors from disk
    and creates an OptimizedLM ready for production use.

    Args:
        graph: The graph whose nodes need predictors.
        compiled_path: Directory containing compiled predictor JSON files.

    Returns:
        OptimizedLM with loaded predictors for available nodes.
    """
    from bae.optimized_lm import OptimizedLM
    from bae.optimizer import load_optimized

    optimized = load_optimized(list(graph.nodes), Path(compiled_path))
    return OptimizedLM(optimized=optimized)
