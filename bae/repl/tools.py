"""ToolRouter: dispatch tool calls to current resource or home filesystem.

Routes read/write/edit/glob/grep to the current resource when navigated in,
falls through to filesystem operations at root. Output over CHAR_CAP is
pruned with structure preservation (headings, tables kept; content trimmed).
"""

from __future__ import annotations

import inspect
import re

from pydantic import ConfigDict, ValidationError, create_model

from bae.repl.spaces import ResourceError, ResourceRegistry, format_unsupported_error

TOKEN_CAP = 500
CHAR_CAP = TOKEN_CAP * 4  # ~4 chars/token heuristic

_STRUCTURAL_RE = re.compile(r"^(#{1,6} |[|]|[=\-]{3,}$|\s*$)")
_LIST_ITEM_RE = re.compile(r"^\s*[-*+] ")


_validator_cache: dict[int, type] = {}


def _build_validator(method) -> type | None:
    """Build a pydantic model from method signature for parameter validation."""
    mid = id(method)
    if mid in _validator_cache:
        return _validator_cache[mid]

    try:
        sig = inspect.signature(method)
    except (ValueError, TypeError):
        _validator_cache[mid] = None
        return None

    fields = {}
    has_var_keyword = False
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                has_var_keyword = True
            continue
        ann = param.annotation if param.annotation is not inspect.Parameter.empty else str
        if param.default is not inspect.Parameter.empty:
            fields[pname] = (ann, param.default)
        else:
            fields[pname] = (ann, ...)

    if not fields:
        _validator_cache[mid] = None
        return None

    if has_var_keyword:
        model = create_model(
            f"{method.__name__}_Params",
            __config__=ConfigDict(extra="allow"),
            **fields,
        )
    else:
        model = create_model(f"{method.__name__}_Params", **fields)
    _validator_cache[mid] = model
    return model


def _validate_tool_params(tool: str, method, arg: str, **kwargs) -> dict | str:
    """Validate tool params via pydantic. Returns validated dict or error string."""
    validator = _build_validator(method)
    if validator is None:
        return {"arg": arg, **kwargs}  # No validation possible, pass through

    # Build the param dict from positional arg + kwargs
    sig = inspect.signature(method)
    param_names = [
        p for p, v in sig.parameters.items()
        if p != "self" and v.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
    ]
    params = {}
    if param_names:
        params[param_names[0]] = arg
    params.update(kwargs)

    try:
        validated = validator(**params)
        return validated.model_dump()
    except ValidationError as e:
        return _format_validation_error(tool, method, e)


def _format_validation_error(tool: str, method, error: ValidationError) -> str:
    """Format pydantic ValidationError into helpful error with method signature."""
    try:
        sig = inspect.signature(method)
        params = []
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            ann = param.annotation
            if ann is not inspect.Parameter.empty:
                tname = ann.__name__ if isinstance(ann, type) else str(ann)
                params.append(f"{pname}: {tname}")
            else:
                params.append(pname)
        sig_str = f"{tool}({', '.join(params)})"
    except Exception:
        sig_str = f"{tool}(...)"

    doc = (getattr(method, "__doc__", None) or "").split("\n")[0].strip()

    # Extract clean error messages from pydantic ValidationError
    error_msgs = "; ".join(e["msg"] for e in error.errors())

    lines = [f"Tool '{tool}' parameter error: {error_msgs}"]
    lines.append(f"Usage: {sig_str}")
    if doc:
        lines.append(f"  {doc}")
    return "\n".join(lines)


class ToolRouter:
    """Route tool calls to current resource or home filesystem."""

    def __init__(self, registry: ResourceRegistry) -> None:
        self._registry = registry

    def dispatch(self, tool: str, arg: str, **kwargs) -> str:
        """Route tool call to current resource or home."""
        current = self._registry.current
        if current is None:
            return self._home_dispatch(tool, arg, **kwargs)

        # Check if resource supports this tool
        if tool not in current.supported_tools():
            return format_unsupported_error(current, tool)

        method = getattr(current, tool)

        # Pydantic validation before execution
        validated = _validate_tool_params(tool, method, arg, **kwargs)
        if isinstance(validated, str):
            return validated  # Validation error message

        # Call with validated params
        try:
            param_names = [
                p for p, v in inspect.signature(method).parameters.items()
                if p != "self" and v.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            ]
            if param_names:
                first_key = param_names[0]
                first_val = validated.pop(first_key)
                result = method(first_val, **validated)
            else:
                result = method()
        except ResourceError as e:
            return str(e)

        return _prune(result)

    def _home_dispatch(self, tool: str, arg: str, **kwargs) -> str:
        """Dispatch to filesystem operations at home."""
        from bae.repl.spaces.home import (
            _exec_glob,
            _exec_grep,
            _exec_read,
        )

        # read() at root with empty arg lists resourcespaces
        if tool == "read" and not arg.strip():
            return self._list_resourcespaces()

        home = {
            "read": _exec_read,
            "glob": _exec_glob,
            "grep": _exec_grep,
        }

        fn = home.get(tool)
        if fn is None:
            return f"Tool '{tool}' not available at home."

        try:
            result = fn(arg)
        except Exception as e:
            return f"Error: {e}"

        return _prune(result)

    def _list_resourcespaces(self) -> str:
        """List registered resourcespaces for read() at root."""
        spaces = self._registry._spaces
        if not spaces:
            return "No resourcespaces registered."
        lines = ["Resourcespaces:"]
        for name, space in sorted(spaces.items()):
            lines.append(f"  @{name}() -- {space.description}")
        return "\n".join(lines)


def _prune(output: str) -> str:
    """Prune output to ~CHAR_CAP chars, preserving structure."""
    if len(output) <= CHAR_CAP:
        return output

    lines = output.split("\n")
    structural: list[tuple[int, str]] = []
    content: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        if _STRUCTURAL_RE.match(line):
            structural.append((i, line))
        else:
            content.append((i, line))

    # Budget: structural lines always kept, fill remaining with content
    structural_chars = sum(len(ln) + 1 for _, ln in structural)
    remaining_budget = CHAR_CAP - structural_chars

    # Keep first N content lines that fit
    kept_content: list[tuple[int, str]] = []
    chars_used = 0
    for idx, line in content:
        line_cost = len(line) + 1
        if chars_used + line_cost > remaining_budget and kept_content:
            break
        kept_content.append((idx, line))
        chars_used += line_cost

    # Always include last content line if not already included
    if content and content[-1] not in kept_content:
        kept_content.append(content[-1])

    # Merge structural + kept content, sorted by original position
    merged = sorted(structural + kept_content, key=lambda x: x[0])
    result_lines = [ln for _, ln in merged]

    total_items = len(content)
    shown_items = len(kept_content)
    result_lines.append(f"[pruned: {total_items} -> {shown_items} items]")

    return "\n".join(result_lines)
