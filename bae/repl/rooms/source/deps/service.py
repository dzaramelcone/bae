"""Deps subresource service: dependency management via pyproject.toml."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

from bae.repl.rooms.view import ResourceError


def read_pyproject(project_root: Path) -> dict:
    path = project_root / "pyproject.toml"
    if not path.exists():
        raise ResourceError("pyproject.toml not found")
    return tomllib.loads(path.read_text())


def read(project_root: Path, target: str = "") -> str:
    data = read_pyproject(project_root)
    deps = data.get("project", {}).get("dependencies", [])
    if not target:
        return "\n".join(deps) if deps else "(no dependencies)"
    matches = [d for d in deps if target.lower() in d.lower()]
    return "\n".join(matches) if matches else f"(no dependency matching '{target}')"


def write(project_root: Path, target: str, content: str = "") -> str:
    result = subprocess.run(
        ["uv", "add", target],
        capture_output=True,
        text=True,
        cwd=project_root,
    )
    if result.returncode != 0:
        raise ResourceError(f"Failed to add {target}: {result.stderr.strip()}")
    return f"Added {target}"


def enter(project_root: Path) -> str:
    data = read_pyproject(project_root)
    deps = data.get("project", {}).get("dependencies", [])
    return f"Project dependencies ({len(deps)} packages)\n\nread() to list, write(name) to add"


def nav(project_root: Path) -> str:
    data = read_pyproject(project_root)
    deps = data.get("project", {}).get("dependencies", [])
    return "\n".join(deps) if deps else "(no dependencies)"
