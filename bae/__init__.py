"""Bae: Type-driven agent graphs with DSPy optimization."""

from bae.compiler import compile_graph, node_to_signature
from bae.dspy_backend import DSPyBackend
from bae.exceptions import BaeError, BaeLMError, BaeParseError
from bae.graph import Graph
from bae.lm import LM, ClaudeCLIBackend, PydanticAIBackend
from bae.markers import Bind, Context, Dep
from bae.node import Node, NodeConfig
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
    "Bind",
    # LM backends
    "LM",
    "DSPyBackend",
    "PydanticAIBackend",
    "ClaudeCLIBackend",
    # Compiler
    "node_to_signature",
    "compile_graph",
    # Exceptions
    "BaeError",
    "BaeParseError",
    "BaeLMError",
]
