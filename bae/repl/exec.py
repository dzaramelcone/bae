"""Async Python execution with top-level await."""

from __future__ import annotations

import ast
import asyncio
import types

_EXPR_CAPTURED = object()


async def async_exec(code: str, namespace: dict) -> object | None:
    """Execute code with PyCF_ALLOW_TOP_LEVEL_AWAIT."""
    tree = ast.parse(code, mode="exec")
    expr_captured = False

    # Capture last expression result in _
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last_expr = tree.body[-1]
        assign = ast.Assign(
            targets=[ast.Name(id="_", ctx=ast.Store())],
            value=last_expr.value,
        )
        tree.body[-1] = assign
        expr_captured = True
        ast.fix_missing_locations(tree)

    compiled = compile(tree, "<cortex>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    fn = types.FunctionType(compiled, namespace)
    result = fn()
    if asyncio.iscoroutine(result):
        await result

    if expr_captured:
        return namespace.get("_")
    return None
