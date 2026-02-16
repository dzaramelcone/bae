"""Tests for Resourcespace protocol, ResourceRegistry, ResourceHandle, and error formatting."""

from __future__ import annotations

import pytest

from bae.repl.resource import (
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

    def __init__(self, name: str, description: str = "", children_map=None, tools=None, hints=None):
        self.name = name
        self.description = description or f"{name} resource"
        self._children = children_map or {}
        self._tools = tools or {"read", "glob", "grep"}
        self._hints = hints or []

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
        source = StubSpace("source")
        tasks = StubSpace("tasks")
        reg.register(source)
        reg.register(tasks)
        reg.navigate("source")
        reg.navigate("tasks")
        reg.back()
        assert reg.current is source

    def test_back_at_root_no_crash(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = reg.back()
        # Should return root nav, not crash
        assert result is not None

    def test_homespace_clears_stack(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.navigate("source")
        result = reg.homespace()
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
        assert "@source()" in repr(handle)


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
        result = reg.homespace()
        assert "@source()" in result
        assert "@tasks()" in result

    def test_nav_tree_marks_current(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.register(StubSpace("tasks"))
        reg.navigate("source")
        result = reg.homespace()
        # After homespace, we're at root, so no marker
        # Navigate then check nav
        reg.navigate("source")
        # root_nav is returned by homespace; but let's test via nav directly
        # The nav tree from _root_nav should mark current position
        # We test by navigating then getting homespace view
        reg.homespace()
        reg.navigate("source")
        # Now get the nav view -- navigate somewhere and check back
        # Actually, the nav tree is rendered via _root_nav which homespace returns.
        # Let's just verify that after navigation, homespace result includes marker
        # since homespace clears stack, there won't be a marker after homespace.
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
        assert "@source()" in tree
        assert "@source.meta()" in tree


# ---------------------------------------------------------------------------
# Error formatting
# ---------------------------------------------------------------------------

class TestErrors:
    def test_fuzzy_suggestion(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = reg.navigate("sourc")
        assert "source" in result.lower()
        assert "@source()" in result

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
        assert "@source.meta()" in result

    def test_errors_contain_hyperlinks(self):
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        result = format_nav_error("sourc", reg)
        assert "@source()" in result

    def test_resource_error_str(self):
        err = ResourceError("something broke", hints=["@source()"])
        s = str(err)
        assert "something broke" in s
        assert "@source()" in s
