"""Bae: Type-driven agent graphs with DSPy optimization."""

from bae.node import Node, NodeConfig
from bae.graph import Graph
from bae.lm import LM, PydanticAIBackend, ClaudeCLIBackend

__all__ = ["Node", "NodeConfig", "Graph", "LM", "PydanticAIBackend", "ClaudeCLIBackend"]
