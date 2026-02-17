"""Home room view: public API for filesystem tools."""

from bae.repl.spaces.home import service


class HomeRoom:
    """Home room: filesystem tools at root context."""

    name = "home"
    description = "Filesystem tools"

    def read(self, target: str = "") -> str:
        return service._exec_read(target)

    def write(self, filepath: str, content: str = "") -> str:
        return service._exec_write(filepath, content)

    def edit_read(self, target: str = "") -> str:
        return service._exec_edit_read(target)

    def edit_replace(
        self, filepath: str, start: int, end: int, content: str = ""
    ) -> str:
        return service._exec_edit_replace(filepath, start, end, content)

    def glob(self, pattern: str = "") -> str:
        return service._exec_glob(pattern)

    def grep(self, pattern: str = "") -> str:
        return service._exec_grep(pattern)
