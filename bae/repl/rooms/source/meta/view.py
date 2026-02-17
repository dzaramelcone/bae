"""Meta subresource view: protocol wrapper delegating to service functions."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from bae.repl.rooms.source.meta import service
from bae.repl.rooms.view import Room


class MetaSubresource:
    """Source room implementation -- reads/edits its own code."""

    name = "meta"
    description = "Source room implementation"

    def __init__(self, project_root: Path) -> None:
        self._root = project_root
        self._module_path = "bae.repl.rooms.source.service"

    def enter(self) -> str:
        return service.enter()

    def nav(self) -> str:
        return service.nav(self._root, self._module_path)

    def read(self, target: str = "") -> str:
        return service.read(self._root, self._module_path, target)

    def edit(self, target: str, new_source: str = "") -> str:
        return service.edit(self._root, self._module_path, target, new_source)

    def supported_tools(self) -> set[str]:
        return {"read", "edit"}

    def tools(self) -> dict[str, Callable]:
        return {"read": self.read, "edit": self.edit}

    def children(self) -> dict[str, Room]:
        return {}
