"""SourceResourcespace: semantic Python project interface via module paths.

Navigates packages, modules, and symbols using dotted Python notation.
All addressing uses module paths (bae.repl.resource) -- no raw file paths
in any output. Read operates at three levels: package listing, module
summary, and symbol source extraction via AST line ranges.
"""

from __future__ import annotations

import ast
from pathlib import Path

from bae.repl.resource import ResourceError, Resourcespace

CHAR_CAP = 2000


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
    """One-line summary: module path, docstring, class/function counts."""
    filepath = _module_to_path(project_root, module_path)
    source = filepath.read_text()
    tree = ast.parse(source)

    docstring = ast.get_docstring(tree) or ""
    first_line = docstring.splitlines()[0] if docstring else "(no docstring)"

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


class _StubSubresource:
    """Minimal Resourcespace stub for not-yet-implemented subresources."""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description

    def enter(self) -> str:
        raise ResourceError(f"{self.name}: not yet implemented")

    def nav(self) -> str:
        raise ResourceError(f"{self.name}: not yet implemented")

    def read(self, target: str = "") -> str:
        raise ResourceError(f"{self.name}: not yet implemented")

    def supported_tools(self) -> set[str]:
        return set()

    def children(self) -> dict[str, Resourcespace]:
        return {}


class SourceResourcespace:
    """Python project source tree -- semantic interface over modules and symbols."""

    name = "source"
    description = "Python project source tree"

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._children = {
            "meta": _StubSubresource("meta", "Resourcespace implementation source"),
            "deps": _StubSubresource("deps", "Project dependencies (pyproject.toml)"),
            "config": _StubSubresource("config", "Project configuration (pyproject.toml)"),
            "tests": _StubSubresource("tests", "Test modules and runner"),
        }

    def enter(self) -> str:
        """Entry display: description, subresources, top-level packages."""
        lines = [f"{self.description}\n"]
        lines.append("Subresources:")
        for name, sub in sorted(self._children.items()):
            lines.append(f"  @source.{name}() -- {sub.description}")
        lines.append("")
        lines.append("Packages:")
        for pkg in _discover_packages(self._root):
            try:
                summary = _module_summary(self._root, pkg)
                lines.append(f"  {summary}")
            except Exception:
                lines.append(f"  {pkg}")
        return "\n".join(lines)

    def nav(self) -> str:
        """Tree of top-level packages and their submodules (one level)."""
        lines = []
        for pkg in _discover_packages(self._root):
            lines.append(pkg)
            pkg_dir = self._root / pkg
            for child in sorted(pkg_dir.iterdir()):
                if child.name.startswith("_") and child.name != "__init__.py":
                    continue
                if child.is_file() and child.name.endswith(".py") and child.name != "__init__.py":
                    mod = _path_to_module(self._root, child)
                    lines.append(f"  {mod}")
                elif child.is_dir() and (child / "__init__.py").exists():
                    mod = _path_to_module(self._root, child / "__init__.py")
                    lines.append(f"  {mod}/")
        return "\n".join(lines)

    def read(self, target: str = "") -> str:
        """Read package listing, module summary, or symbol source."""
        if not target:
            # Root: list top-level packages with summaries
            lines = []
            for pkg in _discover_packages(self._root):
                try:
                    lines.append(_module_summary(self._root, pkg))
                except Exception:
                    lines.append(pkg)
            return "\n".join(lines)

        _validate_module_path(target)

        # Try as module first
        try:
            _module_to_path(self._root, target)
            result = _module_summary(self._root, target)
            if len(result) > CHAR_CAP:
                raise ResourceError(
                    f"Output is {len(result)} chars (cap {CHAR_CAP}). Narrow your read."
                )
            return result
        except ResourceError:
            pass

        # Try as symbol path
        return _read_symbol(self._root, target)

    def supported_tools(self) -> set[str]:
        return {"read", "write", "edit", "glob", "grep"}

    def children(self) -> dict[str, Resourcespace]:
        return dict(self._children)
