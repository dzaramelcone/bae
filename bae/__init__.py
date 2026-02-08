"""Bae: Type-driven agent graphs with DSPy optimization."""

from bae.compiler import compile_graph, create_optimized_lm, node_to_signature
from bae.dspy_backend import DSPyBackend
from bae.optimized_lm import OptimizedLM
from bae.exceptions import BaeError, BaeLMError, BaeParseError, RecallError
from bae.graph import Graph
from bae.lm import LM, ClaudeCLIBackend, PydanticAIBackend
from bae.markers import Bind, Context, Dep, Recall
from bae.node import Node, NodeConfig
from bae.optimizer import (
    load_optimized,
    node_transition_metric,
    optimize_node,
    save_optimized,
    trace_to_examples,
)
from bae.resolver import classify_fields, resolve_fields
from bae.result import GraphResult

__all__ = [
    # Core types
    "Node",
    "NodeConfig",
    "Graph",
    "GraphResult",
    # Markers
    "Context",
    "Dep",
    "Recall",
    "Bind",
    # Resolver
    "classify_fields",
    "resolve_fields",
    # LM backends
    "LM",
    "DSPyBackend",
    "OptimizedLM",
    "PydanticAIBackend",
    "ClaudeCLIBackend",
    # Compiler
    "node_to_signature",
    "compile_graph",
    "create_optimized_lm",
    # Optimizer
    "trace_to_examples",
    "node_transition_metric",
    "optimize_node",
    "save_optimized",
    "load_optimized",
    # Exceptions
    "BaeError",
    "BaeParseError",
    "BaeLMError",
    "RecallError",
]
