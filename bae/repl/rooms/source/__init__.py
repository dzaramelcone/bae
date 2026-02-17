"""Source room: semantic Python project interface via module paths."""

from bae.repl.rooms.source.service import SourceRoom
from bae.repl.rooms.source.deps import DepsSubresource
from bae.repl.rooms.source.config import ConfigSubresource
from bae.repl.rooms.source.tests import TestsSubresource
from bae.repl.rooms.source.meta import MetaSubresource
from bae.repl.rooms.source.models import (
    CHAR_CAP,
    _validate_module_path,
    _module_to_path,
    _path_to_module,
    _module_summary,
    _read_symbol,
    _discover_packages,
    _discover_all_modules,
    _find_symbol,
    _replace_symbol,
    _hot_reload,
    _GLOB_VALID,
)

__all__ = [
    "SourceRoom",
    "DepsSubresource",
    "ConfigSubresource",
    "TestsSubresource",
    "MetaSubresource",
]
