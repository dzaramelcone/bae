"""Config subresource view: protocol wrapper delegating to service functions."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from bae.repl.spaces.source.config import service
from bae.repl.spaces.view import Room


class ConfigSubresource:
    """Project configuration from pyproject.toml."""

    name = "config"
    description = "Project configuration (pyproject.toml)"

    def __init__(self, project_root: Path) -> None:
        self._root = project_root

    def enter(self) -> str:
        return service.enter(self._root)

    def nav(self) -> str:
        return service.nav(self._root)

    def read(self, target: str = "") -> str:
        return service.read(self._root, target)

    def supported_tools(self) -> set[str]:
        return {"read"}

    def tools(self) -> dict[str, Callable]:
        return {"read": self.read}

    def children(self) -> dict[str, Room]:
        return {}
