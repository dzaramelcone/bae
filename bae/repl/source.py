"""SourceResourcespace: semantic Python project interface via module paths.

Navigates packages, modules, and symbols using dotted Python notation.
All addressing uses module paths (bae.repl.resource) -- no raw file paths
in any output. Read operates at three levels: package listing, module
summary, and symbol source extraction via AST line ranges.
"""

from __future__ import annotations

import ast
import fnmatch
import importlib
import re
import subprocess
import textwrap
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


_GLOB_VALID = re.compile(r"^[a-zA-Z0-9_.*]+(\.[a-zA-Z0-9_.*]+)*$")


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

    def write(self, target: str, content: str = "") -> str:
        """Create a new module with validated Python source."""
        _validate_module_path(target)

        # Validate content is valid Python
        try:
            ast.parse(content)
        except SyntaxError as e:
            raise ResourceError(f"Invalid Python: {e}")

        # Resolve filesystem path (module shouldn't exist yet)
        parts = target.split(".")
        filepath = self._root / Path(*parts).with_suffix(".py")
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)

        # Auto-update parent __init__.py
        init_path = filepath.parent / "__init__.py"
        module_name = parts[-1]
        if init_path.exists():
            init_content = init_path.read_text()
            import_line = f"from {target} import *\n"
            if module_name not in init_content:
                try:
                    init_path.write_text(init_content + import_line)
                except Exception:
                    pass  # Skip if __init__.py update fails

        # Hot-reload
        old_source = ""  # New file, rollback means delete
        try:
            _hot_reload(target, filepath, old_source)
        except ResourceError:
            pass  # Reload failure on new module is non-fatal

        return f"Created {target}"

    def edit(self, target: str, new_source: str = "") -> str:
        """Replace a symbol's source by name with AST-based line replacement."""
        _validate_module_path(target)

        # Split into module part and symbol part (same logic as _read_symbol)
        parts = target.split(".")
        for i in range(len(parts), 0, -1):
            mod_path = ".".join(parts[:i])
            try:
                filepath = _module_to_path(self._root, mod_path)
                symbol_parts = parts[i:]
                break
            except ResourceError:
                continue
        else:
            raise ResourceError(f"Module not found for '{target}'")

        if not symbol_parts:
            raise ResourceError(
                f"No symbol specified in '{target}'",
                hints=[f"read('{target}') to see available symbols"],
            )

        # Read current source, save for rollback
        old_source = filepath.read_text()

        # Replace symbol
        new_full = _replace_symbol(old_source, symbol_parts, new_source)

        # Write to disk
        filepath.write_text(new_full)

        # Hot-reload with rollback on failure
        _hot_reload(mod_path, filepath, old_source)

        return f"Edited {'.'.join(symbol_parts)} in {mod_path}"

    def undo(self) -> str:
        """Revert all uncommitted changes via git checkout."""
        result = subprocess.run(
            ["git", "checkout", "--", "."],
            capture_output=True,
            text=True,
            cwd=self._root,
        )
        if result.returncode != 0:
            raise ResourceError(f"Undo failed: {result.stderr}")
        return "Reverted to last committed state"

    def glob(self, pattern: str = "") -> str:
        """Match modules by dotted glob pattern. No filesystem paths in output."""
        if not pattern:
            raise ResourceError("Provide a glob pattern like 'bae.repl.*'")
        if not _GLOB_VALID.match(pattern):
            raise ResourceError(
                f"Invalid glob pattern: '{pattern}'. Use module notation with * wildcards."
            )
        all_modules = _discover_all_modules(self._root)
        matches = [m for m in all_modules if fnmatch.fnmatch(m, pattern)]
        if not matches:
            return "(no matches)"
        result = "\n".join(matches)
        if len(result) > CHAR_CAP:
            raise ResourceError(
                f"Too many matches ({len(matches)}). "
                f"Narrow with a more specific pattern like '{pattern.rsplit('.', 1)[0]}.<subpackage>.*'"
            )
        return result

    def grep(self, pattern: str = "", path: str = "") -> str:
        """Search source content by regex. Returns module:line: content format."""
        if not pattern:
            raise ResourceError("Provide a search pattern")
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ResourceError(f"Invalid regex: {e}")

        # Determine files to search
        if path:
            _validate_module_path(path)
            try:
                filepath = _module_to_path(self._root, path)
                if filepath.name == "__init__.py":
                    # Package: search all modules in it
                    pkg_prefix = path + "."
                    all_mods = _discover_all_modules(self._root)
                    targets = [(m, _module_to_path(self._root, m))
                               for m in all_mods if m == path or m.startswith(pkg_prefix)]
                else:
                    targets = [(path, filepath)]
            except ResourceError:
                raise
        else:
            all_mods = _discover_all_modules(self._root)
            targets = [(m, _module_to_path(self._root, m)) for m in all_mods]

        matches = []
        match_cap = 50
        for mod_path, filepath in targets:
            try:
                lines = filepath.read_text().splitlines()
            except Exception:
                continue
            for lineno, line in enumerate(lines, 1):
                if regex.search(line):
                    matches.append(f"{mod_path}:{lineno}: {line.strip()}")
                    if len(matches) > match_cap:
                        break
            if len(matches) > match_cap:
                break

        if not matches:
            return "(no matches)"

        overflow = len(matches) > match_cap
        if overflow:
            matches = matches[:match_cap]

        result = "\n".join(matches)
        if overflow:
            result += f"\n[{match_cap}+ matches, narrow with path argument]"

        if len(result) > CHAR_CAP:
            raise ResourceError(
                f"Too many matches. Narrow with path argument, e.g. grep('{pattern}', 'bae.repl')"
            )
        return result

    def supported_tools(self) -> set[str]:
        return {"read", "write", "edit", "glob", "grep"}

    def children(self) -> dict[str, Resourcespace]:
        return dict(self._children)
