"""Config subresource service: project configuration from pyproject.toml."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

from bae.repl.rooms.source.models import CHAR_CAP
from bae.repl.rooms.view import ResourceError


def read_pyproject(project_root: Path) -> dict:
    path = project_root / "pyproject.toml"
    if not path.exists():
        raise ResourceError("pyproject.toml not found")
    return tomllib.loads(path.read_text())


def enter(project_root: Path) -> str:
    data = read_pyproject(project_root)
    sections = list(data.keys())
    return f"pyproject.toml ({len(sections)} sections)\n\nSections: {', '.join(sections)}"


def nav(project_root: Path) -> str:
    data = read_pyproject(project_root)
    return "\n".join(data.keys())


def read(project_root: Path, target: str = "") -> str:
    data = read_pyproject(project_root)
    if not target:
        return "\n".join(data.keys())
    if target not in data:
        raise ResourceError(
            f"Section '{target}' not found",
            hints=[f"Available: {', '.join(data.keys())}"],
        )
    result = json.dumps(data[target], indent=2)
    if len(result) > CHAR_CAP:
        raise ResourceError(
            f"Section '{target}' is {len(result)} chars (cap {CHAR_CAP}). "
            "Read a subsection key instead."
        )
    return result
