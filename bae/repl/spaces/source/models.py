"""Source resourcespace domain model helpers.

Module path resolution, AST symbol extraction, package discovery,
symbol replacement, and hot-reload for the source resourcespace.
"""

from __future__ import annotations

import ast
import importlib
import re
import textwrap
from pathlib import Path

from bae.repl.spaces.view import ResourceError

CHAR_CAP = 2000

_GLOB_VALID = re.compile(r"^[a-zA-Z0-9_.*]+(\.[a-zA-Z0-9_.*]+)*$")


def _validate_module_path(path: str) -> None:
    """Reject paths with traversal, filesystem notation, or invalid identifiers."""
    if "/" in path or "\\" in path:
        raise ResourceError(f"Use module notation: '{path}' contains path separators")
    parts = path.split(".")
    for part in parts:
        if not part or not part.isidentifier():
            raise ResourceError(f"Invalid module path: '{path}'")


def _module_to_path(project_root: Path, dotted: str) -> Path:
    """Translate 'bae.repl.resource' to project_root/bae/repl/resource.py."""
    parts = dotted.split(".")
    candidate = project_root / Path(*parts)
    if candidate.is_dir() and (candidate / "__init__.py").exists():
        return candidate / "__init__.py"
    py = candidate.with_suffix(".py")
    if py.exists():
        return py
    raise ResourceError(f"Module '{dotted}' not found")


def _path_to_module(project_root: Path, filepath: Path) -> str:
    """Translate project_root/bae/repl/resource.py to 'bae.repl.resource'."""
    rel = filepath.relative_to(project_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _module_summary(project_root: Path, module_path: str) -> str:
    """One-line summary: module path, docstring, and content counts.

    Packages show subpackage/module counts; plain modules show class/function counts.
    """
    filepath = _module_to_path(project_root, module_path)
    source = filepath.read_text()
    tree = ast.parse(source)

    docstring = ast.get_docstring(tree) or ""
    first_line = docstring.splitlines()[0] if docstring else "(no docstring)"

    if filepath.name == "__init__.py":
        # Package: count immediate children
        pkg_dir = filepath.parent
        subpackages = 0
        modules = 0
        for child in pkg_dir.iterdir():
            if child.is_dir() and (child / "__init__.py").exists():
                subpackages += 1
            elif child.is_file() and child.suffix == ".py" and child.name != "__init__.py":
                modules += 1
        parts = []
        if subpackages:
            parts.append(f"{subpackages} subpackages")
        if modules:
            parts.append(f"{modules} modules")
        counts = ", ".join(parts) if parts else "empty"
        return f"{module_path} -- {first_line} ({counts})"

    classes = [n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef)]
    functions = [
        n
        for n in ast.iter_child_nodes(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not n.name.startswith("_")
    ]

    return f"{module_path} -- {first_line} ({len(classes)} classes, {len(functions)} functions)"


def _read_symbol(project_root: Path, dotted_path: str) -> str:
    """Extract symbol source via AST line ranges."""
    parts = dotted_path.split(".")
    # Walk from longest module prefix to shortest
    for i in range(len(parts), 0, -1):
        mod_path = ".".join(parts[:i])
        try:
            filepath = _module_to_path(project_root, mod_path)
            symbol_parts = parts[i:]
            break
        except ResourceError:
            continue
    else:
        raise ResourceError(f"Module not found for '{dotted_path}'")

    if not symbol_parts:
        raise ResourceError(f"No symbol specified in '{dotted_path}'")

    source = filepath.read_text()
    tree = ast.parse(source)
    lines = source.splitlines()

    # Walk AST to find the symbol (supports nested: Class.method)
    node = tree
    for name in symbol_parts:
        found = None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name == name:
                    found = child
                    break
        if found is None:
            raise ResourceError(
                f"Symbol '{name}' not found in {'.'.join(parts[:i])}",
                hints=[f"read('{'.'.join(parts[:i])}') to see available symbols"],
            )
        node = found

    result = "\n".join(lines[node.lineno - 1 : node.end_lineno])
    if len(result) > CHAR_CAP:
        raise ResourceError(
            f"Symbol source is {len(result)} chars (cap {CHAR_CAP}). Narrow your read.",
            hints=[f"Try a specific method: read('{dotted_path}.<method>')"],
        )
    return result


def _discover_packages(project_root: Path) -> list[str]:
    """Top-level directories under project_root that are Python packages."""
    packages = []
    for child in sorted(project_root.iterdir()):
        if child.is_dir() and (child / "__init__.py").exists():
            packages.append(child.name)
    return packages


def _discover_all_modules(project_root: Path) -> list[str]:
    """All importable .py modules under project_root as dotted paths."""
    modules = []
    for pkg_name in _discover_packages(project_root):
        pkg_dir = project_root / pkg_name
        for py_file in sorted(pkg_dir.rglob("*.py")):
            # Only include files inside proper packages (every parent has __init__.py)
            rel = py_file.relative_to(project_root)
            parts = list(rel.parts)
            # Check all ancestor dirs are packages
            valid = True
            for depth in range(1, len(parts)):
                ancestor = project_root / Path(*parts[:depth])
                if ancestor.is_dir() and not (ancestor / "__init__.py").exists():
                    valid = False
                    break
            if not valid:
                continue
            modules.append(_path_to_module(project_root, py_file))
    return sorted(modules)


def _find_symbol(tree: ast.AST, symbol_parts: list[str]) -> ast.AST | None:
    """Walk AST to find a named symbol (supports dotted: ['Greeter', 'greet'])."""
    node = tree
    for name in symbol_parts:
        found = None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name == name:
                    found = child
                    break
        if found is None:
            return None
        node = found
    return node


def _replace_symbol(source: str, symbol_parts: list[str], new_source: str) -> str:
    """Replace a symbol's source lines, auto-adjusting indentation."""
    tree = ast.parse(source)
    target = _find_symbol(tree, symbol_parts)
    if target is None:
        raise ResourceError(f"Symbol '{'.'.join(symbol_parts)}' not found")

    # Validate new_source parses (wrapped in class body if indented method)
    new_lines = new_source.rstrip("\n").splitlines()
    dedented = textwrap.dedent(new_source)
    try:
        ast.parse(dedented)
    except SyntaxError as e:
        raise ResourceError(f"Invalid Python in new source: {e}")

    # Auto-adjust indentation to match target's col_offset
    target_indent = " " * target.col_offset
    dedented_lines = textwrap.dedent(new_source).rstrip("\n").splitlines()
    adjusted = []
    for line in dedented_lines:
        if line.strip():
            adjusted.append(target_indent + line)
        else:
            adjusted.append("")

    # Replace lines in original source
    lines = source.splitlines()
    result_lines = lines[: target.lineno - 1] + adjusted + lines[target.end_lineno :]
    result = "\n".join(result_lines)
    if source.endswith("\n"):
        result += "\n"

    # Validate entire module still parses
    try:
        ast.parse(result)
    except SyntaxError as e:
        raise ResourceError(f"Edit produces invalid module: {e}")

    return result


def _hot_reload(module_dotted: str, filepath: Path, old_source: str) -> None:
    """Reload module after edit; rollback to old_source on failure."""
    try:
        mod = importlib.import_module(module_dotted)
        importlib.reload(mod)
    except Exception as e:
        filepath.write_text(old_source)
        raise ResourceError(
            f"Reload failed, rolled back: {e}",
            hints=[f"Check {module_dotted} for import errors"],
        )
