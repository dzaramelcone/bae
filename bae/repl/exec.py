"""Async Python execution with top-level await and stdout capture."""

from __future__ import annotations

import ast
import asyncio
import sys
import types
from io import StringIO

_EXPR_CAPTURED = object()


def _ensure_cortex_module(namespace: dict) -> None:
    """Register <cortex> as a module so get_type_hints resolves REPL-defined classes.

    Also sets __name__ in the namespace so classes defined via FunctionType
    get __module__='<cortex>' (Python uses globals()['__name__'] for that).
    """
    namespace.setdefault('__name__', '<cortex>')
    mod = sys.modules.get('<cortex>')
    if mod is None:
        mod = types.ModuleType('<cortex>')
        sys.modules['<cortex>'] = mod
    mod.__dict__.update(namespace)


async def async_exec(code: str, namespace: dict) -> tuple[object | None, str]:
    """Execute code with PyCF_ALLOW_TOP_LEVEL_AWAIT, capturing stdout.

    Returns (result, captured_stdout) where result is the last expression
    value or None, and captured_stdout is any print() output.
    """
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

    _ensure_cortex_module(namespace)
    compiled = compile(tree, "<cortex>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    fn = types.FunctionType(compiled, namespace)

    buf = StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            await result
    finally:
        sys.stdout = old_stdout
    captured = buf.getvalue()

    if expr_captured:
        return namespace.get("_"), captured
    return None, captured
