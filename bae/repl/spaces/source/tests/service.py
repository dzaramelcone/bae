"""Tests subresource service: test suite discovery and search."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from bae.repl.spaces.source.models import CHAR_CAP
from bae.repl.spaces.view import ResourceError


def discover_test_modules(project_root: Path) -> list[str]:
    test_dir = project_root / "tests"
    if not test_dir.exists():
        return []
    modules = []
    for py_file in sorted(test_dir.rglob("*.py")):
        if py_file.name.startswith("test_") or py_file.name == "conftest.py":
            rel = py_file.relative_to(project_root)
            parts = list(rel.parts)
            if parts[-1].endswith(".py"):
                parts[-1] = parts[-1][:-3]
            modules.append(".".join(parts))
    return modules


def enter(project_root: Path) -> str:
    modules = discover_test_modules(project_root)
    return (
        f"Test suite ({len(modules)} modules)\n\n"
        "read() to list modules, grep(pattern) to search tests"
    )


def nav(project_root: Path) -> str:
    modules = discover_test_modules(project_root)
    return "\n".join(modules) if modules else "(no test modules)"


def read(project_root: Path, target: str = "") -> str:
    if not target:
        modules = discover_test_modules(project_root)
        return "\n".join(modules) if modules else "(no test modules)"
    test_dir = project_root / "tests"
    parts = target.replace("tests.", "").split(".")
    filepath = test_dir / (parts[0] + ".py")
    if not filepath.exists():
        raise ResourceError(
            f"Test module '{target}' not found",
            hints=["read() to list available test modules"],
        )
    source = filepath.read_text()
    if len(source) > CHAR_CAP:
        tree = ast.parse(source)
        lines = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                lines.append(f"class {node.name}")
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        lines.append(f"  {child.name}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lines.append(node.name)
        return "\n".join(lines)
    return source


def grep(project_root: Path, pattern: str, path: str = "") -> str:
    """Search test files for pattern."""
    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise ResourceError(f"Invalid regex: {e}")
    test_dir = project_root / "tests"
    if not test_dir.exists():
        return "(no test directory)"
    matches = []
    files = sorted(test_dir.rglob("*.py"))
    if path:
        files = [f for f in files if path in f.name]
    for filepath in files:
        try:
            lines = filepath.read_text().splitlines()
        except Exception:
            continue
        rel = filepath.relative_to(project_root)
        mod = ".".join(rel.with_suffix("").parts)
        for lineno, line in enumerate(lines, 1):
            if regex.search(line):
                matches.append(f"{mod}:{lineno}: {line.strip()}")
                if len(matches) > 50:
                    break
        if len(matches) > 50:
            break
    if not matches:
        return "(no matches)"
    result = "\n".join(matches[:50])
    if len(matches) > 50:
        result += "\n[50+ matches, narrow search]"
    return result
