"""Meta subresource service: reads/edits the source resourcespace's own code."""

from __future__ import annotations

import ast
from pathlib import Path

from bae.repl.spaces.source.models import (
    _hot_reload,
    _module_summary,
    _module_to_path,
    _read_symbol,
    _replace_symbol,
)
from bae.repl.spaces.view import ResourceError


def enter() -> str:
    return (
        "Source resourcespace implementation (bae.repl.spaces.source)\n\n"
        "read() for summary, read(symbol) for symbol source, edit(symbol, new_source) to modify"
    )


def nav(project_root: Path, module_path: str) -> str:
    filepath = _module_to_path(project_root, module_path)
    source = filepath.read_text()
    tree = ast.parse(source)
    lines = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            lines.append(f"class {node.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(node.name)
    return "\n".join(lines)


def read(project_root: Path, module_path: str, target: str = "") -> str:
    if not target:
        return _module_summary(project_root, module_path)
    return _read_symbol(project_root, f"{module_path}.{target}")


def edit(project_root: Path, module_path: str, target: str, new_source: str = "") -> str:
    """Edit a symbol in the source module."""
    filepath = _module_to_path(project_root, module_path)
    old_source = filepath.read_text()
    symbol_parts = target.split(".")
    new_full = _replace_symbol(old_source, symbol_parts, new_source)
    filepath.write_text(new_full)
    _hot_reload(module_path, filepath, old_source)
    return f"Edited {target} in {module_path}"
