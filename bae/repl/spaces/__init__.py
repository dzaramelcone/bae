"""Room packages: protocol re-exports and sub-packages.

Protocol types are defined in bae.repl.spaces.view. This __init__ re-exports
them so downstream code can use `from bae.repl.spaces import Room, ...`.
"""

from bae.repl.spaces.view import (
    NavResult,
    ResourceError,
    ResourceHandle,
    ResourceRegistry,
    Room,
    format_nav_error,
    format_unsupported_error,
    MAX_STACK_DEPTH,
    _TOOL_NAMES,
)
