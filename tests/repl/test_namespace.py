"""Tests for REPL namespace seeding and NsInspector introspection."""

from __future__ import annotations

import asyncio
import inspect
import os
import textwrap
from typing import Annotated
from unittest.mock import MagicMock

import pytest

from bae.graph import Graph
from bae.markers import Dep, Recall
from bae.node import Node
from bae.repl.namespace import NsInspector, seed


# --- Test fixtures using real bae types ---


def fetch_weather() -> str:
    return "sunny"


class StartNode(Node):
    """Analyze the request and decide next step."""

    request: str

    async def __call__(self) -> MiddleNode | EndNode:
        ...


class MiddleNode(Node):
    """Process the analysis."""

    data: str
    weather: Annotated[str, Dep(fetch_weather)]

    async def __call__(self) -> EndNode | None:
        ...


class EndNode(Node):
    """Terminal node with recalled data."""

    summary: str
    prior: Annotated[str, Recall()]

    async def __call__(self) -> None:
        ...


@pytest.fixture
def graph():
    return Graph(start=StartNode)


@pytest.fixture
def ns_dict():
    return seed()


@pytest.fixture
def inspector(ns_dict):
    return ns_dict["ns"]


# --- seed() tests ---


def test_seed_contains_core_types(ns_dict):
    """seed() includes Node, Graph, Dep, Recall."""
    from bae import Node as BaeNode, Graph as BaeGraph, Dep as BaeDep, Recall as BaeRecall

    assert ns_dict["Node"] is BaeNode
    assert ns_dict["Graph"] is BaeGraph
    assert ns_dict["Dep"] is BaeDep
    assert ns_dict["Recall"] is BaeRecall


def test_seed_contains_extras(ns_dict):
    """seed() includes GraphResult, LM, NodeConfig."""
    from bae import GraphResult, LM, NodeConfig

    assert ns_dict["GraphResult"] is GraphResult
    assert ns_dict["LM"] is LM
    assert ns_dict["NodeConfig"] is NodeConfig


def test_seed_contains_annotated(ns_dict):
    """seed() includes typing.Annotated for field annotations."""
    assert ns_dict["Annotated"] is Annotated


def test_seed_contains_stdlib(ns_dict):
    """seed() includes asyncio and os modules."""
    assert ns_dict["asyncio"] is asyncio
    assert ns_dict["os"] is os


def test_seed_contains_builtins(ns_dict):
    """seed() includes __builtins__."""
    assert "__builtins__" in ns_dict


def test_seed_contains_ns_inspector(ns_dict):
    """seed() includes 'ns' key bound to NsInspector."""
    assert "ns" in ns_dict
    assert isinstance(ns_dict["ns"], NsInspector)


def test_seed_ns_inspector_bound_to_dict(ns_dict):
    """NsInspector is bound to the same dict seed() returns."""
    inspector = ns_dict["ns"]
    assert inspector._ns is ns_dict


# --- NsInspector.__repr__ ---


def test_inspector_repr(inspector):
    """NsInspector repr shows helpful usage hint."""
    assert repr(inspector) == "ns() -- inspect namespace. ns(obj) -- inspect object."


# --- NsInspector() / ns() -- list all ---


def test_list_all_skips_underscore_keys(inspector, ns_dict, capsys):
    """ns() skips keys starting with underscore."""
    ns_dict["_secret"] = "hidden"
    inspector()
    output = capsys.readouterr().out
    assert "_secret" not in output
    assert "__builtins__" not in output


def test_list_all_shows_non_underscore_entries(inspector, capsys):
    """ns() prints entries for non-underscore namespace keys."""
    inspector()
    output = capsys.readouterr().out
    assert "Node" in output
    assert "Graph" in output
    assert "Dep" in output
    assert "Recall" in output
    assert "ns" in output


def test_list_all_shows_class_type_label(inspector, capsys):
    """ns() labels types as 'class'."""
    inspector()
    output = capsys.readouterr().out
    # Find line with Node
    lines = output.strip().splitlines()
    node_line = [l for l in lines if l.strip().startswith("Node")][0]
    assert "class" in node_line


def test_list_all_shows_instance_type_label(inspector, ns_dict, capsys):
    """ns() labels instances with type(obj).__name__."""
    ns_dict["mylist"] = [1, 2, 3]
    inspector()
    output = capsys.readouterr().out
    lines = output.strip().splitlines()
    list_line = [l for l in lines if "mylist" in l][0]
    assert "list" in list_line


def test_list_all_sorted_alphabetically(inspector, capsys):
    """ns() output is sorted alphabetically by name."""
    inspector()
    output = capsys.readouterr().out
    lines = output.strip().splitlines()
    names = [l.split()[0] for l in lines if l.strip()]
    assert names == sorted(names)


def test_list_all_column_aligned(inspector, ns_dict, capsys):
    """ns() output columns are aligned."""
    # Add a short-named entry to test alignment padding
    ns_dict["x"] = 42
    inspector()
    output = capsys.readouterr().out
    lines = output.strip().splitlines()
    assert len(lines) >= 2
    # The format is "  {name:<N}  {type:<M}  {summary}" -- the second column
    # position should be identical across all lines. Use regex to find column 2.
    import re
    # Match leading indent + name + spaces + type_label
    # Column 2 starts after "  {padded_name}  "
    col2_positions = []
    for line in lines:
        # Find the position where the non-space text after the first column starts
        m = re.match(r"^  (\S+)(\s+)(\S+)", line)
        if m:
            col2_positions.append(m.start(3))
    assert len(set(col2_positions)) == 1, f"Columns not aligned: positions={col2_positions}"


# --- NsInspector(graph) -- graph inspection ---


def test_inspect_graph_shows_start(inspector, graph, capsys):
    """ns(graph) prints Graph(start=StartNode)."""
    inspector(graph)
    output = capsys.readouterr().out
    assert "Graph(start=StartNode)" in output


def test_inspect_graph_shows_node_count(inspector, graph, capsys):
    """ns(graph) prints node count."""
    inspector(graph)
    output = capsys.readouterr().out
    assert f"Nodes: {len(graph.nodes)}" in output


def test_inspect_graph_shows_edges(inspector, graph, capsys):
    """ns(graph) prints node edges."""
    inspector(graph)
    output = capsys.readouterr().out
    assert "StartNode ->" in output
    assert "MiddleNode" in output
    assert "EndNode" in output


def test_inspect_graph_shows_terminal_marker(inspector, graph, capsys):
    """ns(graph) shows (terminal) for nodes without successors."""
    inspector(graph)
    output = capsys.readouterr().out
    assert "(terminal)" in output


def test_inspect_graph_shows_terminals_list(inspector, graph, capsys):
    """ns(graph) prints Terminals line with terminal node names."""
    inspector(graph)
    output = capsys.readouterr().out
    assert "Terminals:" in output
    assert "EndNode" in output


# --- NsInspector(NodeSubclass) -- node class inspection ---


def test_inspect_node_class_header(inspector, capsys):
    """ns(NodeClass) prints ClassName(Node)."""
    inspector(StartNode)
    output = capsys.readouterr().out
    assert "StartNode(Node)" in output


def test_inspect_node_class_docstring(inspector, capsys):
    """ns(NodeClass) prints first line of docstring."""
    inspector(StartNode)
    output = capsys.readouterr().out
    assert "Analyze the request and decide next step." in output


def test_inspect_node_class_successors(inspector, capsys):
    """ns(NodeClass) prints successors."""
    inspector(StartNode)
    output = capsys.readouterr().out
    assert "Successors:" in output
    assert "MiddleNode" in output
    assert "EndNode" in output


def test_inspect_node_class_terminal_status(inspector, capsys):
    """ns(NodeClass) shows Terminal: yes/no."""
    inspector(StartNode)
    start_output = capsys.readouterr().out
    assert "Terminal: no" in start_output

    inspector(EndNode)
    end_output = capsys.readouterr().out
    assert "Terminal: yes" in end_output


def test_inspect_node_class_fields(inspector, capsys):
    """ns(NodeClass) lists fields with kind."""
    inspector(MiddleNode)
    output = capsys.readouterr().out
    assert "Fields:" in output
    assert "data" in output
    assert "plain" in output
    assert "weather" in output
    assert "dep" in output


def test_inspect_node_class_dep_annotation(inspector, capsys):
    """ns(NodeClass) shows Dep(fn_name) for dep fields."""
    inspector(MiddleNode)
    output = capsys.readouterr().out
    assert "Dep(fetch_weather)" in output


def test_inspect_node_class_recall_annotation(inspector, capsys):
    """ns(NodeClass) shows Recall() for recall fields."""
    inspector(EndNode)
    output = capsys.readouterr().out
    assert "Recall()" in output


# --- NsInspector(node_instance) -- instance inspection ---


def test_inspect_node_instance_shows_class_info(inspector, capsys):
    """ns(node_instance) shows class fields like ns(NodeClass)."""
    instance = StartNode(request="test")
    inspector(instance)
    output = capsys.readouterr().out
    assert "StartNode(Node)" in output
    assert "Fields:" in output


def test_inspect_node_instance_shows_values(inspector, capsys):
    """ns(node_instance) shows current field values."""
    instance = StartNode(request="hello world")
    inspector(instance)
    output = capsys.readouterr().out
    assert "Values:" in output
    assert "request" in output
    assert "'hello world'" in output


# --- NsInspector(other) -- generic fallback ---


def test_inspect_generic_object(inspector, capsys):
    """ns(other_obj) prints type and repr."""
    inspector(42)
    output = capsys.readouterr().out
    assert "int" in output
    assert "42" in output


def test_inspect_generic_truncates_long_repr(inspector, capsys):
    """ns(other_obj) truncates repr to 200 chars."""
    long_obj = "x" * 500
    inspector(long_obj)
    output = capsys.readouterr().out
    assert len(output.strip()) <= 250  # some slack for type prefix


# --- _one_liner helper (tested through _list_all) ---


def test_one_liner_type_uses_docstring(inspector, ns_dict, capsys):
    """_one_liner for a class with docstring uses its first line."""
    ns_dict["StartNode"] = StartNode
    inspector()
    output = capsys.readouterr().out
    lines = output.strip().splitlines()
    start_line = [l for l in lines if l.strip().startswith("StartNode")][0]
    assert "Analyze the request" in start_line


def test_one_liner_module_shows_module(inspector, capsys):
    """_one_liner for a module uses the module name."""
    inspector()
    output = capsys.readouterr().out
    lines = output.strip().splitlines()
    asyncio_line = [l for l in lines if l.strip().startswith("asyncio")][0]
    assert "module" in asyncio_line.lower() or "asyncio" in asyncio_line


def test_one_liner_ns_inspector(inspector, capsys):
    """_one_liner for NsInspector shows usage hint."""
    inspector()
    output = capsys.readouterr().out
    lines = output.strip().splitlines()
    ns_line = [l for l in lines if l.strip().startswith("ns ")][0]
    assert "inspect" in ns_line.lower() or "namespace" in ns_line.lower()


# --- REPL-defined class annotation resolution ---


async def test_inspect_repl_defined_node_class(capsys):
    """ns(NodeClass) works for classes defined via async_exec (REPL simulation).

    Classes defined in the REPL get __module__='<cortex>' from compile().
    _ensure_cortex_module registers <cortex> in sys.modules so
    get_type_hints() can resolve Annotated/Dep/Recall annotations.
    """
    from bae.repl.exec import async_exec

    ns = seed()
    # Define a Node subclass as the REPL would -- via async_exec
    code = textwrap.dedent("""\
        class TestNode(Node):
            query: str
            info: Annotated[str, Dep()]

            async def __call__(self) -> None: ...
    """)
    await async_exec(code, ns)

    test_cls = ns["TestNode"]
    assert test_cls.__module__ == "<cortex>"

    # ns(TestNode) must not crash -- it calls classify_fields + get_type_hints
    inspector = ns["ns"]
    inspector(test_cls)
    output = capsys.readouterr().out

    assert "TestNode(Node)" in output
    assert "query" in output
    assert "plain" in output
    assert "info" in output
    assert "dep" in output
