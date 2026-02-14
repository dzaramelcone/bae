"""REPL namespace seeding and introspection.

seed() builds the initial namespace dict with bae types pre-loaded.
NsInspector provides ns() for listing and ns(obj) for deep inspection.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import textwrap
from typing import Annotated, get_args, get_origin, get_type_hints

import bae
from bae.graph import Graph
from bae.markers import Dep
from bae.node import Node
from bae.resolver import classify_fields


# Objects pre-loaded into the REPL namespace.
_PRELOADED = {
    "Node": bae.Node,
    "Graph": bae.Graph,
    "Dep": bae.Dep,
    "Recall": bae.Recall,
    "GraphResult": bae.GraphResult,
    "LM": bae.LM,
    "NodeConfig": bae.NodeConfig,
    "Annotated": Annotated,
    "asyncio": asyncio,
    "os": os,
}


def seed() -> dict:
    """Build the initial REPL namespace with bae objects pre-loaded."""
    ns: dict = {"__builtins__": __builtins__}
    ns.update(_PRELOADED)
    ns["ns"] = NsInspector(ns)
    return ns


def _one_liner(obj: object) -> str:
    """One-line summary for namespace listing."""
    if isinstance(obj, NsInspector):
        return "ns() -- inspect namespace"
    if isinstance(obj, type):
        if obj.__doc__:
            return obj.__doc__.strip().splitlines()[0]
        return obj.__name__
    if inspect.ismodule(obj):
        return obj.__name__
    if callable(obj) and not isinstance(obj, type):
        return getattr(obj, "__qualname__", None) or repr(obj)
    return textwrap.shorten(repr(obj), width=60)


class NsInspector:
    """Namespace introspection tool.

    ns()        -- list all namespace objects with types and summaries
    ns(graph)   -- show graph topology (nodes, edges)
    ns(MyNode)  -- show node fields with annotations
    ns(obj)     -- show type and attributes of any object
    """

    def __init__(self, namespace: dict) -> None:
        self._ns = namespace

    def __call__(self, obj=None):
        if obj is None:
            self._list_all()
        elif isinstance(obj, Graph):
            self._inspect_graph(obj)
        elif isinstance(obj, type) and issubclass(obj, Node):
            self._inspect_node_class(obj)
        elif isinstance(obj, Node):
            self._inspect_node_instance(obj)
        else:
            self._inspect_generic(obj)

    def __repr__(self):
        return "ns() -- inspect namespace. ns(obj) -- inspect object."

    def _list_all(self):
        """Print column-aligned table of all non-underscore namespace entries."""
        items = []
        for name, obj in sorted(self._ns.items()):
            if name.startswith("_"):
                continue
            if isinstance(obj, type):
                type_label = "class"
            else:
                type_label = type(obj).__name__
            summary = _one_liner(obj)
            items.append((name, type_label, summary))

        if not items:
            print("(namespace is empty)")
            return

        max_name = max(len(i[0]) for i in items)
        max_type = max(len(i[1]) for i in items)
        for name, type_label, summary in items:
            print(f"  {name:<{max_name}}  {type_label:<{max_type}}  {summary}")

    def _inspect_graph(self, graph: Graph):
        """Print graph topology: start, nodes, edges, terminals."""
        print(f"Graph(start={graph.start.__name__})")
        print(f"  Nodes: {len(graph.nodes)}")
        for node_cls in sorted(graph.nodes, key=lambda n: n.__name__):
            succs = graph.edges.get(node_cls, set())
            if succs:
                succ_str = ", ".join(sorted(s.__name__ for s in succs))
            else:
                succ_str = "(terminal)"
            print(f"    {node_cls.__name__} -> {succ_str}")
        terminals = graph.terminal_nodes
        if terminals:
            print(f"  Terminals: {', '.join(sorted(n.__name__ for n in terminals))}")

    def _inspect_node_class(self, node_cls: type[Node]):
        """Print node class fields with type, kind, and annotations."""
        print(f"{node_cls.__name__}(Node)")
        if node_cls.__doc__:
            print(f"  {node_cls.__doc__.strip().splitlines()[0]}")

        succs = node_cls.successors()
        if succs:
            print(f"  Successors: {' | '.join(sorted(s.__name__ for s in succs))}")
        print(f"  Terminal: {'yes' if node_cls.is_terminal() else 'no'}")

        fields = classify_fields(node_cls)
        model_fields = node_cls.model_fields
        if model_fields:
            print("  Fields:")
            max_name = max(len(n) for n in model_fields)
            hints = get_type_hints(node_cls, include_extras=True)
            for name in model_fields:
                kind = fields.get(name, "plain")
                # Extract base type from Annotated if needed
                hint = hints.get(name)
                if hint and get_origin(hint) is Annotated:
                    base = get_args(hint)[0]
                else:
                    base = hint
                type_name = getattr(base, "__name__", str(base)) if base else "?"
                marker = ""
                if kind == "dep":
                    # Find the Dep marker to get fn name
                    if hint and get_origin(hint) is Annotated:
                        for m in get_args(hint)[1:]:
                            if isinstance(m, Dep):
                                fn_name = getattr(m.fn, "__name__", "auto") if m.fn else "auto"
                                marker = f"  Dep({fn_name})"
                                break
                elif kind == "recall":
                    marker = "  Recall()"
                print(f"    {name:<{max_name}}  {type_name}  {kind}{marker}")

    def _inspect_node_instance(self, instance: Node):
        """Print node class info plus current field values."""
        self._inspect_node_class(type(instance))
        values = instance.model_dump()
        if values:
            print("  Values:")
            max_name = max(len(n) for n in values)
            for name, value in values.items():
                print(f"    {name:<{max_name}} = {repr(value)}")

    def _inspect_generic(self, obj: object):
        """Print type and repr, truncated to 200 chars."""
        r = repr(obj)
        print(f"{type(obj).__name__}: {textwrap.shorten(r, width=200)}")
