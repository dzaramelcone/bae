"""Source resourcespace service: SourceResourcespace.

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
from pathlib import Path
from string.templatelib import Template
from typing import Callable

from bae.repl.spaces.view import ResourceError, Resourcespace
from bae.repl.spaces.source.models import (
    CHAR_CAP,
    _GLOB_VALID,
    _discover_all_modules,
    _discover_packages,
    _hot_reload,
    _module_summary,
    _module_to_path,
    _path_to_module,
    _read_symbol,
    _replace_symbol,
    _validate_module_path,
)
from bae.repl.spaces.source.deps import DepsSubresource
from bae.repl.spaces.source.config import ConfigSubresource
from bae.repl.spaces.source.tests import TestsSubresource
from bae.repl.spaces.source.meta import MetaSubresource


def _render(template: Template) -> str:
    """Render a tstring template to a plain string."""
    parts = []
    for i, s in enumerate(template.strings):
        parts.append(s)
        if i < len(template.interpolations):
            parts.append(str(template.interpolations[i].value))
    return "".join(parts)


def _subresource_templates(name: str, description: str) -> dict[str, Template]:
    """Tstring templates for a new subresource package."""
    cls = name.title() + "Subresource"
    return {
        "__init__.py": t'from bae.repl.spaces.source.{name}.view import {cls}\n\n__all__ = ["{cls}"]\n',
        "view.py": t'"""{description} subresource view: protocol wrapper delegating to service functions."""\n\nfrom __future__ import annotations\n\nfrom pathlib import Path\nfrom typing import Callable\n\nfrom bae.repl.spaces.source.{name} import service\nfrom bae.repl.spaces.view import Resourcespace\n\n\nclass {cls}:\n    """{description}."""\n\n    name = "{name}"\n    description = "{description}"\n\n    def __init__(self, project_root: Path) -> None:\n        self._root = project_root\n\n    def enter(self) -> str:\n        return "{description}\\n\\nread() for details"\n\n    def nav(self) -> str:\n        return ""\n\n    def read(self, target: str = "") -> str:\n        return service.read(self._root, target)\n\n    def supported_tools(self) -> set[str]:\n        return {{"read"}}\n\n    def tools(self) -> dict[str, Callable]:\n        return {{"read": self.read}}\n\n    def children(self) -> dict[str, Resourcespace]:\n        return {{}}\n',
        "service.py": t'"""{description} service implementations."""\n\nfrom __future__ import annotations\n\nfrom pathlib import Path\n\n\ndef read(project_root: Path, target: str = "") -> str:\n    return "(not yet implemented)"\n',
    }


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
        """Create a new module or subresource package.

        Simple identifier (no dots): creates a subresource package from tstring template.
        Dotted path: creates a plain module with validated Python source.
        """
        _validate_module_path(target)

        # Simple identifier = new subresource package
        if "." not in target:
            return self._write_subresource(target, content)

        # Dotted path = plain module creation
        try:
            ast.parse(content)
        except SyntaxError as e:
            raise ResourceError(f"Invalid Python: {e}")

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

    def _write_subresource(self, name: str, description: str = "") -> str:
        """Create a new subresource package from tstring template."""
        if name in self._children:
            raise ResourceError(f"Subresource '{name}' already exists")

        description = description or name.replace("_", " ").title()
        pkg_dir = Path(__file__).parent / name
        if pkg_dir.exists():
            raise ResourceError(f"Directory '{name}' already exists under source/")

        templates = _subresource_templates(name, description)
        pkg_dir.mkdir()
        for filename, template in templates.items():
            (pkg_dir / filename).write_text(_render(template))

        # Auto-register into children (dynamic import of the view class)
        module_path = f"bae.repl.spaces.source.{name}.view"
        cls_name = name.title() + "Subresource"
        try:
            mod = __import__(module_path, fromlist=[cls_name])
            cls = getattr(mod, cls_name)
            self._children[name] = cls(self._root)
        except Exception:
            pass  # Registration failure is non-fatal; restart will pick it up

        return f"Created subresource '{name}' at source/{name}/"

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

        if path:
            filepath = _module_to_path(self._root, path)
            if filepath.is_dir():
                # Package: search all modules in it
                pkg_prefix = path + "."
                all_mods = _discover_all_modules(self._root)
                targets = [(m, _module_to_path(self._root, m))
                           for m in all_mods if m == path or m.startswith(pkg_prefix)]
            else:
                # Single module
                targets = [(path, filepath)]
        else:
            all_mods = _discover_all_modules(self._root)
            targets = [(m, _module_to_path(self._root, m)) for m in all_mods]

        matches = []
        match_cap = 50
        for mod_path, filepath in targets:
            try:
                source = filepath.read_text()
            except Exception:
                continue
            for lineno, line in enumerate(source.splitlines(), 1):
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
            if path:
                raise ResourceError(
                    f"Too many matches. Narrow with a more specific regex pattern."
                )
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
