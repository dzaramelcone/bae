"""Source resourcespace: semantic Python project interface via module paths."""

from bae.repl.spaces.source.service import (
    SourceResourcespace,
    DepsSubresource,
    ConfigSubresource,
    TestsSubresource,
    MetaSubresource,
)
from bae.repl.spaces.source.models import (
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
