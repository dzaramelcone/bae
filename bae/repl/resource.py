"""Resourcespace protocol, registry, navigation, handles, and error formatting.

Provides the foundation for v7.0 resourcespace navigation. Resources are
self-describing domains the agent navigates by calling them as functions.
The registry tracks navigation state as a stack and renders entry displays,
nav trees, and error messages with @resource() hyperlinks.
"""

from __future__ import annotations

import difflib
from typing import Callable, Protocol, runtime_checkable

from rich.tree import Tree

from bae.repl.views import _rich_to_ansi


class NavResult(str):
    """String whose repr() outputs raw content, preserving ANSI rendering.

    _run_py displays expression results via repr(result). Normal str repr
    escapes ANSI codes (\\x1b becomes \\\\x1b). NavResult.__repr__ returns
    self so ANSI passes through to the terminal.
    """

    def __repr__(self) -> str:
        return str(self)


MAX_STACK_DEPTH = 20


@runtime_checkable
class Resourcespace(Protocol):
    """A navigable domain that responds to standard tool verbs."""

    name: str
    description: str

    def enter(self) -> str:
        """Entry display: functions table, state, breadcrumb, Python hints."""
        ...

    def nav(self) -> str:
        """Indented tree view of navigable structure from current position."""
        ...

    def read(self, target: str = "") -> str:
        """Read a resource. Returns content string."""
        ...

    def supported_tools(self) -> set[str]:
        """Which standard tools this resource supports."""
        ...

    def children(self) -> dict[str, Resourcespace]:
        """Subresourcespaces for dotted navigation."""
        ...

    def tools(self) -> dict[str, Callable]:
        """Tool callables keyed by standard tool name. Injected into namespace on navigate."""
        ...


class ResourceError(Exception):
    """Protocol-level error with navigation hints."""

    def __init__(self, message: str, hints: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hints = hints or []

    def __str__(self) -> str:
        parts = [self.message]
        if self.hints:
            parts.append("Try: " + ", ".join(self.hints))
        return "\n".join(parts)


_TOOL_NAMES = frozenset({"read", "write", "edit", "glob", "grep"})


class ResourceRegistry:
    """Flat registry of resourcespaces with stack-based navigation."""

    def __init__(self, namespace: dict | None = None) -> None:
        self._spaces: dict[str, Resourcespace] = {}
        self._stack: list[Resourcespace] = []
        self._namespace = namespace

    @property
    def current(self) -> Resourcespace | None:
        return self._stack[-1] if self._stack else None

    def register(self, space: Resourcespace) -> None:
        """Register a resourcespace by its name."""
        self._spaces[space.name] = space

    def navigate(self, target: str) -> str:
        """Navigate to target (supports dotted paths). Returns entry display or error."""
        parts = target.split(".")
        root_name = parts[0]

        # Resolve root
        space = self._spaces.get(root_name)
        if space is None:
            return format_nav_error(target, self)

        # Build navigation chain
        chain = [space]
        resolved_chain = space
        for child_name in parts[1:]:
            kids = resolved_chain.children()
            if child_name not in kids:
                return format_nav_error(target, self)
            resolved_chain = kids[child_name]
            chain.append(resolved_chain)

        # Transition message
        prev = self.current
        transition = ""
        if prev is not None and prev is not chain[-1]:
            transition = f"Left {prev.name} -> entering {chain[-1].name}\n\n"

        # Replace stack from divergence point (not append)
        common = 0
        for i in range(min(len(self._stack), len(chain))):
            if self._stack[i] is chain[i]:
                common = i + 1
            else:
                break
        self._stack = self._stack[:common] + chain[common:]

        if len(self._stack) > MAX_STACK_DEPTH:
            self._stack = self._stack[-MAX_STACK_DEPTH:]

        self._put_tools()
        return NavResult(transition + self._entry_display(chain[-1]))

    def back(self) -> str:
        """Pop navigation stack. Returns entry display of parent or root nav."""
        if self._stack:
            self._stack.pop()
        self._put_tools()
        if self._stack:
            return NavResult(self._entry_display(self._stack[-1]))
        return self._root_nav()

    def homespace(self) -> str:
        """Clear stack, return root nav tree."""
        self._stack.clear()
        self._put_tools()
        return self._root_nav()

    def breadcrumb(self) -> str:
        """Navigation path: 'home > source > meta'."""
        parts = ["home"]
        for space in self._stack:
            parts.append(space.name)
        return " > ".join(parts)

    def _put_tools(self) -> None:
        """Put current resource's tools into namespace. Idempotent."""
        if self._namespace is None:
            return
        for name in _TOOL_NAMES:
            self._namespace.pop(name, None)
        current = self.current
        if current is not None:
            self._namespace.update(current.tools())

    def _root_nav(self) -> str:
        """Render nav tree from root using Rich Tree."""
        tree = Tree("[bold]home[/bold]")
        current = self.current

        for name, space in sorted(self._spaces.items()):
            label = f"{name}()"
            if space is current:
                label += "  <-- you are here"
            branch = tree.add(label)

            kids = space.children()
            shown = 0
            for child_name, child_space in sorted(kids.items()):
                child_label = f"{name}.{child_name}()"
                if child_space is current:
                    child_label += "  <-- you are here"
                branch.add(child_label)
                shown += 1
                # Cap tree depth at 2 levels; collapse deeper children
                grandkids = child_space.children()
                if grandkids:
                    branch_child = branch.children[-1] if branch.children else branch
                    remaining = len(grandkids)
                    branch_child.add(f"+{remaining} more")

        return NavResult(_rich_to_ansi(tree).rstrip())

    def _entry_display(self, space: Resourcespace) -> str:
        """Breadcrumb + description + state + functions table + Advanced hints."""
        lines = [self.breadcrumb()]
        entry = space.enter()

        # Split entry into main content and Advanced block
        entry_lines = entry.split("\n")
        main_lines = []
        advanced_lines = []
        in_advanced = False
        for line in entry_lines:
            if line.strip().startswith("Advanced:"):
                in_advanced = True
                advanced_lines.append(line)
            elif in_advanced:
                advanced_lines.append(line)
            else:
                main_lines.append(line)

        # Description / state from enter()
        if main_lines:
            lines.append("\n".join(main_lines))

        # Functions table
        tools = sorted(space.supported_tools())
        if tools:
            lines.append("")
            lines.append("| Tool | Function | Returns |")
            lines.append("|------|----------|---------|")
            for tool in tools:
                lines.append(f"| {tool} | {tool}() | {tool} result |")

        # Advanced hints
        if advanced_lines:
            lines.append("")
            lines.extend(advanced_lines)

        return "\n".join(lines)


class ResourceHandle:
    """Callable namespace object that navigates on call."""

    def __init__(self, name: str, registry: ResourceRegistry) -> None:
        self._name = name
        self._registry = registry

    def __call__(self) -> str:
        return self._registry.navigate(self._name)

    def __getattr__(self, child: str) -> ResourceHandle:
        """Enable dotted access: source.meta()."""
        if child.startswith("_"):
            raise AttributeError(child)
        return ResourceHandle(f"{self._name}.{child}", self._registry)

    def __repr__(self) -> str:
        return f"{self._name}() -- navigate to {self._name}"


def format_unsupported_error(space: Resourcespace, tool: str) -> str:
    """Error for unsupported tool with nav hint to the right child resource."""
    hints = []
    for child_name, child_space in space.children().items():
        if tool in child_space.supported_tools():
            hints.append(f"{space.name}.{child_name}()")

    err = ResourceError(
        f"{space.name} does not support {tool}.",
        hints=hints,
    )
    return NavResult(str(err))


def format_nav_error(target: str, registry: ResourceRegistry) -> str:
    """Error for bad navigation target with fuzzy suggestion."""
    names = list(registry._spaces.keys())
    matches = difflib.get_close_matches(target.split(".")[0], names, n=1, cutoff=0.5)

    if matches:
        suggestion = matches[0]
        err = ResourceError(
            f"No resource '{target}'. Did you mean {suggestion}()?",
            hints=[f"{suggestion}()"],
        )
    else:
        err = ResourceError(f"No resource '{target}'.")
    return NavResult(str(err))
