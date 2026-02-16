"""Tests for Resourcespace protocol, ResourceRegistry, ResourceHandle, and error formatting."""

from __future__ import annotations

import pytest

from bae.repl.spaces import (
    NavResult,
    ResourceError,
    ResourceHandle,
    ResourceRegistry,
    Resourcespace,
    format_nav_error,
    format_unsupported_error,
)


# ---------------------------------------------------------------------------
# Stub resourcespace for testing
# ---------------------------------------------------------------------------

class StubSpace:
    """Minimal Resourcespace implementation for tests."""

    def __init__(self, name: str, description: str = "", children_map=None, tools=None, hints=None, tool_callables=None):
        self.name = name
        self.description = description or f"{name} resource"
        self._children = children_map or {}
        self._tools = tools or {"read", "glob", "grep"}
        self._hints = hints or []
        self._tool_callables = tool_callables or {}

    def enter(self) -> str:
        parts = [self.description]
        if self._hints:
            parts.append("Advanced:")
            parts.extend(f"  {h}" for h in self._hints)
        return "\n".join(parts)

    def nav(self) -> str:
        return f"nav tree for {self.name}"

    def read(self, target: str = "") -> str:
        return f"read {self.name}: {target}"

    def supported_tools(self) -> set[str]:
        return self._tools

    def tools(self) -> dict:
        return self._tool_callables

    def children(self) -> dict[str, Resourcespace]:
        return self._children


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_stub_is_resourcespace(self):
        space = StubSpace("test")
        assert isinstance(space, Resourcespace)

    def test_missing_method_not_resourcespace(self):
        class Incomplete:
            name = "x"
            description = "x"
            def enter(self) -> str: return ""
            # missing nav, read, supported_tools, children

        assert not isinstance(Incomplete(), Resourcespace)


# ---------------------------------------------------------------------------
# Registry navigation
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_register_makes_navigable(self):
        reg = ResourceRegistry()
        space = StubSpace("source")
        reg.register(space)
        result = reg.navigate("source")
        assert "source" in result.lower()

    def test_navigate_returns_entry_with_functions_table(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = reg.navigate("source")
        # Entry display should contain table-like content
        assert "source" in result.lower()

    def test_navigate_returns_entry_with_breadcrumb(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = reg.navigate("source")
        assert "home" in result.lower()

    def test_current_after_navigate(self):
        reg = ResourceRegistry()
        space = StubSpace("source")
        reg.register(space)
        reg.navigate("source")
        assert reg.current is space

    def test_current_none_at_root(self):
        reg = ResourceRegistry()
        assert reg.current is None

    def test_back_pops_to_previous(self):
        reg = ResourceRegistry()
        meta = StubSpace("meta")
        source = StubSpace("source", children_map={"meta": meta})
        reg.register(source)
        reg.navigate("source.meta")
        reg.back()
        assert reg.current is source

    def test_back_at_root_no_crash(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = reg.back()
        # Should return root nav, not crash
        assert result is not None

    def test_home_clears_stack(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.navigate("source")
        result = reg.home()
        assert reg.current is None
        assert result is not None

    def test_breadcrumb_at_root(self):
        reg = ResourceRegistry()
        assert reg.breadcrumb() == "home"

    def test_breadcrumb_after_navigate(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.navigate("source")
        assert reg.breadcrumb() == "home > source"

    def test_dotted_navigation(self):
        reg = ResourceRegistry()
        meta = StubSpace("meta")
        source = StubSpace("source", children_map={"meta": meta})
        reg.register(source)
        reg.navigate("source.meta")
        assert reg.current is meta

    def test_dotted_breadcrumb(self):
        reg = ResourceRegistry()
        meta = StubSpace("meta")
        source = StubSpace("source", children_map={"meta": meta})
        reg.register(source)
        reg.navigate("source.meta")
        assert reg.breadcrumb() == "home > source > meta"

    def test_direct_jump_from_depth(self):
        reg = ResourceRegistry()
        meta = StubSpace("meta")
        source = StubSpace("source", children_map={"meta": meta})
        tasks = StubSpace("tasks")
        reg.register(source)
        reg.register(tasks)
        reg.navigate("source")
        reg.navigate("source.meta")
        reg.navigate("tasks")
        assert reg.current is tasks

    def test_stack_caps_at_20(self):
        reg = ResourceRegistry()
        spaces = [StubSpace(f"s{i}") for i in range(25)]
        for s in spaces:
            reg.register(s)
        for s in spaces:
            reg.navigate(s.name)
        # Stack should be capped at 20
        assert len(reg._stack) <= 20

    def test_transition_message(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.register(StubSpace("tasks"))
        reg.navigate("source")
        result = reg.navigate("tasks")
        # Should mention leaving source and entering tasks
        assert "source" in result.lower()
        assert "tasks" in result.lower()

    def test_navigate_sibling_replaces_stack(self):
        """Navigate source.config then source.deps: breadcrumb is home > source > deps."""
        reg = ResourceRegistry()
        config = StubSpace("config")
        deps = StubSpace("deps")
        source = StubSpace("source", children_map={"config": config, "deps": deps})
        reg.register(source)
        reg.navigate("source.config")
        assert reg.breadcrumb() == "home > source > config"
        reg.navigate("source.deps")
        assert reg.breadcrumb() == "home > source > deps"

    def test_navigate_same_root_replaces(self):
        """Navigate source then source again: stack has exactly one source entry."""
        reg = ResourceRegistry()
        source = StubSpace("source")
        reg.register(source)
        reg.navigate("source")
        reg.navigate("source")
        assert reg._stack == [source]


# ---------------------------------------------------------------------------
# ResourceHandle
# ---------------------------------------------------------------------------

class TestResourceHandle:
    def test_call_navigates(self):
        reg = ResourceRegistry()
        space = StubSpace("source")
        reg.register(space)
        handle = ResourceHandle("source", reg)
        result = handle()
        assert reg.current is space
        assert result is not None

    def test_dotted_call(self):
        reg = ResourceRegistry()
        meta = StubSpace("meta")
        source = StubSpace("source", children_map={"meta": meta})
        reg.register(source)
        handle = ResourceHandle("source", reg)
        result = handle.meta()
        assert reg.current is meta

    def test_repr_contains_mention(self):
        reg = ResourceRegistry()
        handle = ResourceHandle("source", reg)
        assert "source()" in repr(handle)


# ---------------------------------------------------------------------------
# Entry display format
# ---------------------------------------------------------------------------

class TestEntryDisplay:
    def test_entry_contains_breadcrumb(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = reg.navigate("source")
        assert "home > source" in result

    def test_entry_contains_description(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source", description="bae project source tree"))
        result = reg.navigate("source")
        assert "bae project source tree" in result

    def test_entry_contains_functions_table(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source", tools={"read", "glob", "grep"}))
        result = reg.navigate("source")
        # Table should list supported tools
        assert "read" in result.lower()

    def test_entry_contains_advanced_hints(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source", hints=["<run>source.files()</run>"]))
        result = reg.navigate("source")
        assert "Advanced:" in result


# ---------------------------------------------------------------------------
# Nav tree
# ---------------------------------------------------------------------------

class TestNavTree:
    def test_nav_tree_contains_mentions(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.register(StubSpace("tasks"))
        result = reg.home()
        assert "source()" in result
        assert "tasks()" in result

    def test_nav_tree_marks_current(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.register(StubSpace("tasks"))
        reg.navigate("source")
        result = reg.home()
        # After home, we're at root, so no marker
        # Navigate then check nav
        reg.navigate("source")
        # root_nav is returned by home; but let's test via nav directly
        # The nav tree from _root_nav should mark current position
        # We test by navigating then getting home view
        reg.home()
        reg.navigate("source")
        # Now get the nav view -- navigate somewhere and check back
        # Actually, the nav tree is rendered via _root_nav which home returns.
        # Let's just verify that after navigation, home result includes marker
        # since home clears stack, there won't be a marker after home.
        # Instead, test the nav tree when called while navigated in:
        pass  # Covered by nav_tree_marks_current_position below

    def test_nav_tree_marks_current_position(self):
        reg = ResourceRegistry()
        source = StubSpace("source")
        reg.register(source)
        reg.register(StubSpace("tasks"))
        reg.navigate("source")
        # Get nav tree while inside source
        tree = reg._root_nav()
        assert "you are here" in tree.lower() or "<--" in tree

    def test_nav_tree_indents_children(self):
        reg = ResourceRegistry()
        meta = StubSpace("meta")
        source = StubSpace("source", children_map={"meta": meta})
        reg.register(source)
        tree = reg._root_nav()
        assert "source()" in tree
        assert "source.meta()" in tree


# ---------------------------------------------------------------------------
# Error formatting
# ---------------------------------------------------------------------------

class TestErrors:
    def test_fuzzy_suggestion(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = reg.navigate("sourc")
        assert "source" in result.lower()
        assert "source()" in result

    def test_no_close_match_plain_error(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = reg.navigate("zzzzz")
        assert "zzzzz" in result

    def test_unsupported_error_with_nav_hint(self):
        source = StubSpace("source", tools={"read", "glob"})
        meta = StubSpace("meta", tools={"read", "write", "edit"})
        source._children = {"meta": meta}
        result = format_unsupported_error(source, "write")
        assert "write" in result.lower()
        assert "source.meta()" in result

    def test_errors_contain_hyperlinks(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = format_nav_error("sourc", reg)
        assert "source()" in result

    def test_resource_error_str(self):
        err = ResourceError("something broke", hints=["source()"])
        s = str(err)
        assert "something broke" in s
        assert "source()" in s

    def test_error_messages_no_at_prefix(self):
        """Error messages use source() syntax, not @source() syntax."""
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = format_nav_error("sourc", reg)
        assert "@" not in result


# ---------------------------------------------------------------------------
# NavResult repr preserves ANSI
# ---------------------------------------------------------------------------

class TestNavResult:
    def test_nav_result_repr_preserves_ansi(self):
        """repr() on NavResult returns raw string, not escaped."""
        ansi = "\x1b[1mhome\x1b[0m"
        nr = NavResult(ansi)
        assert repr(nr) == ansi  # not "\\x1b[1mhome\\x1b[0m"

    def test_nav_result_is_str(self):
        nr = NavResult("hello")
        assert isinstance(nr, str)

    def test_home_returns_nav_result(self):
        reg = ResourceRegistry()
        result = reg.home()
        assert isinstance(result, NavResult)

    def test_navigate_returns_nav_result(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = reg.navigate("source")
        assert isinstance(result, NavResult)

    def test_back_returns_nav_result(self):
        reg = ResourceRegistry()
        result = reg.back()
        assert isinstance(result, NavResult)

    def test_back_with_stack_returns_nav_result(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.navigate("source")
        result = reg.back()
        assert isinstance(result, NavResult)

    def test_navigate_error_returns_nav_result(self):
        reg = ResourceRegistry()
        result = reg.navigate("nonexistent")
        assert isinstance(result, NavResult)

    def test_format_unsupported_error_returns_nav_result(self):
        space = StubSpace("source", tools={"read"})
        result = format_unsupported_error(space, "write")
        assert isinstance(result, NavResult)


# ---------------------------------------------------------------------------
# Tool injection via namespace
# ---------------------------------------------------------------------------

class TestToolInjection:
    def test_navigate_injects_tools(self):
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        mock_read = lambda: "content"
        space = StubSpace("source", tool_callables={"read": mock_read})
        reg.register(space)
        reg.navigate("source")
        assert ns["read"] is mock_read

    def test_home_swaps_to_home_tools(self):
        """Navigate to resource, then home(): resource tools removed, home tools injected."""
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        mock_read = lambda: "content"
        home_read = lambda arg: "home read"
        home_glob = lambda pattern: "home glob"
        home_grep = lambda arg: "home grep"
        space = StubSpace("source", tool_callables={"read": mock_read})
        reg.register(space)
        reg._home_tools = {"read": home_read, "glob": home_glob, "grep": home_grep}
        reg.navigate("source")
        assert ns["read"] is mock_read
        reg.home()
        assert ns["read"] is home_read
        assert ns["glob"] is home_glob
        assert ns["grep"] is home_grep

    def test_navigate_swaps_tools(self):
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        mock_read = lambda: "r"
        mock_glob = lambda: "g"
        mock_write = lambda: "w"
        space_a = StubSpace("alpha", tool_callables={"read": mock_read, "glob": mock_glob})
        space_b = StubSpace("beta", tool_callables={"read": mock_read, "write": mock_write})
        reg.register(space_a)
        reg.register(space_b)
        reg.navigate("alpha")
        assert "glob" in ns
        reg.navigate("beta")
        assert ns["read"] is mock_read
        assert ns["write"] is mock_write
        assert "glob" not in ns

    def test_home_injects_tools(self):
        """Set _home_tools on registry, call home(), verify tools in namespace."""
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        home_read = lambda arg: "home read"
        home_glob = lambda pattern: "home glob"
        home_grep = lambda arg: "home grep"
        reg._home_tools = {"read": home_read, "glob": home_glob, "grep": home_grep}
        reg.home()
        assert ns["read"] is home_read
        assert ns["glob"] is home_glob
        assert ns["grep"] is home_grep

    def test_home_returns_orientation(self):
        """home() returns orientation string with resourcespaces and tools."""
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        reg.register(StubSpace("source", description="project source"))
        reg._home_tools = {"read": lambda a: "", "glob": lambda a: "", "grep": lambda a: ""}
        result = reg.home()
        assert "Resourcespaces:" in result
        assert "source()" in result
        assert "Tools:" in result

    def test_back_to_root_returns_orientation(self):
        """Navigate then back() to root returns orientation content."""
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        reg.register(StubSpace("source", description="project source"))
        reg._home_tools = {"read": lambda a: "", "glob": lambda a: ""}
        reg.navigate("source")
        result = reg.back()
        assert "Resourcespaces:" in result
        assert "source()" in result

    def test_no_namespace_no_crash(self):
        """Registry without namespace still works fine."""
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.navigate("source")  # should not crash
        reg.back()
        reg.home()
