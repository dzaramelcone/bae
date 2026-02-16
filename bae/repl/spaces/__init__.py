"""Resourcespace packages: protocol re-exports and sub-packages.

Import protocol types from bae.repl.resource so downstream code can
use `from bae.repl.spaces import Resourcespace, ResourceRegistry, ...`.
"""

from bae.repl.resource import (
    NavResult,
    ResourceError,
    ResourceHandle,
    ResourceRegistry,
    Resourcespace,
    format_nav_error,
    format_unsupported_error,
    MAX_STACK_DEPTH,
    _TOOL_NAMES,
)
