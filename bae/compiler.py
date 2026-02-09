"""DSPy compiler for graph optimization.

Compiles a Graph into a DSPy program for prompt optimization.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, get_type_hints

import dspy

from bae.graph import Graph, _get_base_type
from bae.node import Node
from bae.resolver import classify_fields


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

    async def run(self, start_node: Node) -> "GraphResult":
        """Run the compiled graph using optimized predictors.

        Creates an OptimizedLM from loaded predictors and delegates
        to Graph.run(). Nodes with optimized predictors use them;
        others fall back to naive prompts.

        Args:
            start_node: The initial node to start execution.

        Returns:
            GraphResult with final node and execution trace.
        """
        from bae.optimized_lm import OptimizedLM
        from bae.result import GraphResult

        lm = OptimizedLM(optimized=self.optimized)
        return await self.graph.run(start_node, lm=lm)

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


def node_to_signature(
    node_cls: type[Node],
    is_start: bool = False,
) -> type[dspy.Signature]:
    """Convert a Node class to a DSPy Signature.

    Uses classify_fields() to determine InputField vs OutputField mapping:
    - Dep fields -> InputField (context from external sources)
    - Recall fields -> InputField (context from trace)
    - Plain fields + is_start -> InputField (caller-provided)
    - Plain fields + not is_start -> OutputField (LLM fills)

    Instruction is built from class name only — docstrings are inert (Phase 10).

    Args:
        node_cls: The node class to convert.
        is_start: Whether this is the start node. When True, plain fields
            become InputFields (caller-provided) instead of OutputFields.

    Returns:
        A dspy.Signature subclass with the appropriate fields.
    """
    classifications = classify_fields(node_cls)
    hints = get_type_hints(node_cls, include_extras=True)
    fields: dict[str, tuple[type, dspy.InputField | dspy.OutputField]] = {}

    for name, kind in classifications.items():
        base_type = _get_base_type(hints[name])

        if kind in ("dep", "recall"):
            fields[name] = (base_type, dspy.InputField())
        elif is_start:
            # Plain field on start node -> caller-provided
            fields[name] = (base_type, dspy.InputField())
        else:
            # Plain field on non-start node -> LLM fills
            fields[name] = (base_type, dspy.OutputField())

    # Build instruction from class name only — docstrings are inert (Phase 10)
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
