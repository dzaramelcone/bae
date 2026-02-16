"""Source resourcespace service: SourceResourcespace and subresources.

Navigates packages, modules, and symbols using dotted Python notation.
All addressing uses module paths (bae.repl.resource) -- no raw file paths
in any output. Read operates at three levels: package listing, module
summary, and symbol source extraction via AST line ranges.
"""

from __future__ import annotations

import ast
import fnmatch
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Callable

from bae.repl.resource import ResourceError, Resourcespace
from bae.repl.spaces.source.models import (
    CHAR_CAP,
    _GLOB_VALID,
    _discover_all_modules,
    _discover_packages,
    _find_symbol,
    _hot_reload,
    _module_summary,
    _module_to_path,
    _path_to_module,
    _read_symbol,
    _replace_symbol,
    _validate_module_path,
)


class DepsSubresource:
    """Project dependencies from pyproject.toml."""

    name = "deps"
    description = "Project dependencies"

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def _read_pyproject(self) -> dict:
        path = self._root / "pyproject.toml"
        if not path.exists():
            raise ResourceError("pyproject.toml not found")
        return tomllib.loads(path.read_text())

    def enter(self) -> str:
        data = self._read_pyproject()
        deps = data.get("project", {}).get("dependencies", [])
        return f"Project dependencies ({len(deps)} packages)\n\nread() to list, write(name) to add"

    def nav(self) -> str:
        data = self._read_pyproject()
        deps = data.get("project", {}).get("dependencies", [])
        return "\n".join(deps) if deps else "(no dependencies)"

    def read(self, target: str = "") -> str:
        data = self._read_pyproject()
        deps = data.get("project", {}).get("dependencies", [])
        if not target:
            return "\n".join(deps) if deps else "(no dependencies)"
        matches = [d for d in deps if target.lower() in d.lower()]
        return "\n".join(matches) if matches else f"(no dependency matching '{target}')"

    def write(self, target: str, content: str = "") -> str:
        result = subprocess.run(
            ["uv", "add", target],
            capture_output=True,
            text=True,
            cwd=self._root,
        )
        if result.returncode != 0:
            raise ResourceError(f"Failed to add {target}: {result.stderr.strip()}")
        return f"Added {target}"

    def supported_tools(self) -> set[str]:
        return {"read", "write"}

    def tools(self) -> dict[str, Callable]:
        return {"read": self.read, "write": self.write}

    def children(self) -> dict[str, Resourcespace]:
        return {}


class ConfigSubresource:
    """Project configuration from pyproject.toml."""

    name = "config"
    description = "Project configuration (pyproject.toml)"

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def _read_pyproject(self) -> dict:
        path = self._root / "pyproject.toml"
        if not path.exists():
            raise ResourceError("pyproject.toml not found")
        return tomllib.loads(path.read_text())

    def enter(self) -> str:
        data = self._read_pyproject()
        sections = list(data.keys())
        return f"pyproject.toml ({len(sections)} sections)\n\nSections: {', '.join(sections)}"

    def nav(self) -> str:
        data = self._read_pyproject()
        return "\n".join(data.keys())

    def read(self, target: str = "") -> str:
        data = self._read_pyproject()
        if not target:
            return "\n".join(data.keys())
        if target not in data:
            raise ResourceError(
                f"Section '{target}' not found",
                hints=[f"Available: {', '.join(data.keys())}"],
            )
        import json

        result = json.dumps(data[target], indent=2)
        if len(result) > CHAR_CAP:
            raise ResourceError(
                f"Section '{target}' is {len(result)} chars (cap {CHAR_CAP}). "
                "Read a subsection key instead."
            )
        return result

    def supported_tools(self) -> set[str]:
        return {"read"}

    def tools(self) -> dict[str, Callable]:
        return {"read": self.read}

    def children(self) -> dict[str, Resourcespace]:
        return {}


class TestsSubresource:
    """Test suite discovery and search."""

    name = "tests"
    description = "Test suite"

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def _test_dir(self) -> Path:
        return self._root / "tests"

    def _discover_test_modules(self) -> list[str]:
        test_dir = self._test_dir()
        if not test_dir.exists():
            return []
        modules = []
        for py_file in sorted(test_dir.rglob("*.py")):
            if py_file.name.startswith("test_") or py_file.name == "conftest.py":
                rel = py_file.relative_to(self._root)
                parts = list(rel.parts)
                if parts[-1].endswith(".py"):
                    parts[-1] = parts[-1][:-3]
                modules.append(".".join(parts))
        return modules

    def enter(self) -> str:
        modules = self._discover_test_modules()
        return (
            f"Test suite ({len(modules)} modules)\n\n"
            "read() to list modules, grep(pattern) to search tests"
        )

    def nav(self) -> str:
        modules = self._discover_test_modules()
        return "\n".join(modules) if modules else "(no test modules)"

    def read(self, target: str = "") -> str:
        if not target:
            modules = self._discover_test_modules()
            return "\n".join(modules) if modules else "(no test modules)"
        # Read specific test module
        test_dir = self._test_dir()
        # target could be like "test_source" or "tests.test_source"
        parts = target.replace("tests.", "").split(".")
        filepath = test_dir / (parts[0] + ".py")
        if not filepath.exists():
            raise ResourceError(
                f"Test module '{target}' not found",
                hints=["read() to list available test modules"],
            )
        source = filepath.read_text()
        if len(source) > CHAR_CAP:
            # Show summary instead
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

    def grep(self, pattern: str, path: str = "") -> str:
        """Search test files for pattern."""
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ResourceError(f"Invalid regex: {e}")
        test_dir = self._test_dir()
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
            rel = filepath.relative_to(self._root)
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

    def supported_tools(self) -> set[str]:
        return {"read", "grep"}

    def tools(self) -> dict[str, Callable]:
        return {"read": self.read, "grep": self.grep}

    def children(self) -> dict[str, Resourcespace]:
        return {}


class MetaSubresource:
    """Source resourcespace implementation -- reads/edits its own code."""

    name = "meta"
    description = "Source resourcespace implementation"

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._module_path = "bae.repl.spaces.source.service"

    def _source_file(self) -> Path:
        return _module_to_path(self._root, self._module_path)

    def enter(self) -> str:
        return (
            "Source resourcespace implementation (bae.repl.spaces.source.service)\n\n"
            "read() for summary, read(symbol) for symbol source, edit(symbol, new_source) to modify"
        )

    def nav(self) -> str:
        filepath = self._source_file()
        source = filepath.read_text()
        tree = ast.parse(source)
        lines = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                lines.append(f"class {node.name}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lines.append(node.name)
        return "\n".join(lines)

    def read(self, target: str = "") -> str:
        if not target:
            return _module_summary(self._root, self._module_path)
        # Read a specific symbol from source.py
        return _read_symbol(self._root, f"{self._module_path}.{target}")

    def edit(self, target: str, new_source: str = "") -> str:
        """Edit a symbol in source.py."""
        filepath = self._source_file()
        old_source = filepath.read_text()
        symbol_parts = target.split(".")
        new_full = _replace_symbol(old_source, symbol_parts, new_source)
        filepath.write_text(new_full)
        _hot_reload(self._module_path, filepath, old_source)
        return f"Edited {target} in {self._module_path}"

    def supported_tools(self) -> set[str]:
        return {"read", "edit"}

    def tools(self) -> dict[str, Callable]:
        return {"read": self.read, "edit": self.edit}

    def children(self) -> dict[str, Resourcespace]:
        return {}


class SourceResourcespace:
    """Python project source tree -- semantic interface over modules and symbols."""

    name = "source"
    description = "Python project source tree"

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._children = {
            "meta": MetaSubresource(project_root),
            "deps": DepsSubresource(project_root),
            "config": ConfigSubresource(project_root),
            "tests": TestsSubresource(project_root),
        }

    def enter(self) -> str:
        """Entry display: description, subresources, top-level packages."""
        lines = [f"{self.description}\n"]
        lines.append("Subresources:")
        for name, sub in sorted(self._children.items()):
            lines.append(f"  source.{name}() -- {sub.description}")
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

    def tools(self) -> dict[str, Callable]:
        return {
            "read": self.read,
            "write": self.write,
            "edit": self.edit,
            "glob": self.glob,
            "grep": self.grep,
        }

    def children(self) -> dict[str, Resourcespace]:
        return dict(self._children)
