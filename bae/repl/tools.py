"""ToolRouter: dispatch tool calls to current resource or homespace filesystem.

Routes read/write/edit/glob/grep to the current resource when navigated in,
falls through to filesystem operations at root. Output over CHAR_CAP is
pruned with structure preservation (headings, tables kept; content trimmed).
"""

from __future__ import annotations

import re

from bae.repl.resource import ResourceError, ResourceRegistry, format_unsupported_error

TOKEN_CAP = 500
CHAR_CAP = TOKEN_CAP * 4  # ~4 chars/token heuristic

_STRUCTURAL_RE = re.compile(r"^(#{1,6} |[|]|[=\-]{3,}$|\s*$)")
_LIST_ITEM_RE = re.compile(r"^\s*[-*+] ")


class ToolRouter:
    """Route tool calls to current resource or homespace filesystem."""

    def __init__(self, registry: ResourceRegistry) -> None:
        self._registry = registry

    def dispatch(self, tool: str, arg: str, **kwargs) -> str:
        """Route tool call to current resource or homespace."""
        current = self._registry.current
        if current is None:
            return self._homespace_dispatch(tool, arg, **kwargs)

        # Check if resource supports this tool
        if tool not in current.supported_tools():
            return format_unsupported_error(current, tool)

        # Call resource method
        try:
            method = getattr(current, tool)
            result = method(arg, **kwargs)
        except ResourceError as e:
            return str(e)

        return _prune(result)

    def _homespace_dispatch(self, tool: str, arg: str, **kwargs) -> str:
        """Dispatch to filesystem operations at root."""
        from bae.repl.ai import (
            _exec_glob,
            _exec_grep,
            _exec_read,
        )

        # read() at root with empty arg lists resourcespaces
        if tool == "read" and not arg.strip():
            return self._list_resourcespaces()

        homespace = {
            "read": _exec_read,
            "glob": _exec_glob,
            "grep": _exec_grep,
        }

        fn = homespace.get(tool)
        if fn is None:
            return f"Tool '{tool}' not available at homespace root."

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
