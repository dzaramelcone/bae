"""Bae: Type-driven agent graphs."""

from bae.exceptions import BaeError, BaeLMError, BaeParseError, DepError, FillError, RecallError
from bae.graph import Graph
from bae.lm import LM, ClaudeCLIBackend
from bae.markers import Dep, Effect, Recall
from bae.node import Node, NodeConfig
from bae.resolver import classify_fields, resolve_fields
from bae.result import GraphResult

__all__ = [
    # Core types
    "Node",
    "NodeConfig",
    "Graph",
    "GraphResult",
    # Markers
    "Dep",
    "Effect",
    "Recall",
    # Resolver
    "classify_fields",
    "resolve_fields",
    # LM backends
    "LM",
    "ClaudeCLIBackend",
    # Exceptions
    "BaeError",
    "BaeParseError",
    "BaeLMError",
    "DepError",
    "FillError",
    "RecallError",
]
