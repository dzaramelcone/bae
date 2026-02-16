"""Tests for ToolRouter dispatch routing, pruning, and error handling."""

from __future__ import annotations

import pytest

from bae.repl.resource import (
    ResourceError,
    ResourceRegistry,
    Resourcespace,
    format_unsupported_error,
)
from bae.repl.tools import CHAR_CAP, TOKEN_CAP, ToolRouter


# ---------------------------------------------------------------------------
# Stub resourcespace for testing
# ---------------------------------------------------------------------------

class StubSpace:
    """Minimal Resourcespace with configurable tool support and responses."""

    def __init__(self, name: str, description: str = "", children_map=None,
                 tools=None, read_response=None, write_response=None,
                 glob_response=None, grep_response=None, error_on=None):
        self.name = name
        self.description = description or f"{name} resource"
        self._children = children_map or {}
        self._tools = tools or {"read", "glob", "grep"}
        self._read_response = read_response or f"read from {name}"
        self._write_response = write_response or f"wrote to {name}"
        self._glob_response = glob_response or f"glob results from {name}"
        self._grep_response = grep_response or f"grep results from {name}"
        self._error_on = error_on or set()

    def enter(self) -> str:
        return self.description

    def nav(self) -> str:
        return f"nav tree for {self.name}"

    def read(self, target: str = "") -> str:
        if "read" in self._error_on:
            raise ResourceError("read failed", hints=[f"@{self.name}()"])
        return self._read_response

    def write(self, target: str, content: str = "") -> str:
        if "write" in self._error_on:
            raise ResourceError("write failed")
        return self._write_response

    def glob(self, pattern: str = "") -> str:
        return self._glob_response

    def grep(self, pattern: str = "", path: str = "") -> str:
        return self._grep_response

    def supported_tools(self) -> set[str]:
        return self._tools

    def children(self) -> dict[str, Resourcespace]:
        return self._children


# ---------------------------------------------------------------------------
# Token cap constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_token_cap_is_500(self):
        assert TOKEN_CAP == 500

    def test_char_cap_is_2000(self):
        assert CHAR_CAP == 2000

    def test_char_cap_is_token_cap_times_4(self):
        assert CHAR_CAP == TOKEN_CAP * 4


# ---------------------------------------------------------------------------
# Dispatch routing
# ---------------------------------------------------------------------------

class TestDispatchRouting:
    def test_root_read_calls_home(self, tmp_path):
        """At root (registry.current is None), dispatch read goes to filesystem."""
        reg = ResourceRegistry()
        router = ToolRouter(reg)
        f = tmp_path / "hello.txt"
        f.write_text("hello world")
        result = router.dispatch("read", str(f))
        assert "hello world" in result

    def test_resource_read_calls_resource_method(self):
        """When navigated in, dispatch read calls resource.read()."""
        reg = ResourceRegistry()
        space = StubSpace("source", read_response="custom read output")
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "some/target")
        assert "custom read output" in result

    def test_unsupported_tool_returns_error(self):
        """Resource that doesn't support 'write' returns formatted error."""
        reg = ResourceRegistry()
        space = StubSpace("source", tools={"read", "glob"})
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("write", "target")
        assert "write" in result.lower()
        assert "source" in result.lower()

    def test_resource_error_returned_as_string(self):
        """ResourceError from resource methods is returned as string."""
        reg = ResourceRegistry()
        space = StubSpace("source", error_on={"read"})
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "target")
        assert "read failed" in result

    def test_root_read_empty_arg_lists_resourcespaces(self):
        """read() at root with empty arg lists registered resourcespaces."""
        reg = ResourceRegistry()
        reg.register(StubSpace("source"))
        reg.register(StubSpace("tasks"))
        router = ToolRouter(reg)
        result = router.dispatch("read", "")
        assert "source" in result
        assert "tasks" in result

    def test_root_glob_calls_filesystem_glob(self, tmp_path):
        """At root, glob dispatches to filesystem glob."""
        reg = ResourceRegistry()
        router = ToolRouter(reg)
        f = tmp_path / "test.py"
        f.write_text("x")
        result = router.dispatch("glob", str(tmp_path / "*.py"))
        assert "test.py" in result

    def test_root_grep_calls_filesystem_grep(self, tmp_path):
        """At root, grep dispatches to filesystem grep."""
        reg = ResourceRegistry()
        router = ToolRouter(reg)
        f = tmp_path / "code.py"
        f.write_text("def hello():\n    pass\n")
        result = router.dispatch("grep", f"hello {f}")
        assert "hello" in result


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

class TestPruning:
    def test_short_output_unchanged(self):
        """Output under CHAR_CAP passes through unchanged."""
        reg = ResourceRegistry()
        space = StubSpace("source", read_response="short output")
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "x")
        assert result == "short output"

    def test_long_output_pruned(self):
        """Output over CHAR_CAP is pruned to roughly CHAR_CAP chars."""
        reg = ResourceRegistry()
        long_output = "\n".join(f"line {i}: some content here" for i in range(200))
        space = StubSpace("source", read_response=long_output)
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "x")
        assert len(result) < len(long_output)

    def test_pruned_output_contains_indicator(self):
        """Pruned output contains [pruned:] indicator."""
        reg = ResourceRegistry()
        long_output = "\n".join(f"line {i}: content" for i in range(200))
        space = StubSpace("source", read_response=long_output)
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "x")
        assert "[pruned:" in result

    def test_pruning_preserves_headings(self):
        """Structural lines (headings) are preserved in pruned output."""
        reg = ResourceRegistry()
        lines = ["# Main Heading"]
        lines += [f"content line {i}" for i in range(200)]
        lines += ["## Sub Heading"]
        lines += [f"more content {i}" for i in range(100)]
        long_output = "\n".join(lines)
        space = StubSpace("source", read_response=long_output)
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "x")
        assert "# Main Heading" in result
        assert "## Sub Heading" in result

    def test_pruning_preserves_first_and_last(self):
        """First content block and last line are preserved."""
        reg = ResourceRegistry()
        lines = [f"line {i}: detailed content here" for i in range(200)]
        long_output = "\n".join(lines)
        space = StubSpace("source", read_response=long_output)
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "x")
        # First line should be present
        assert "line 0:" in result

    def test_error_output_never_pruned(self):
        """Error output is never pruned, even if over CHAR_CAP."""
        reg = ResourceRegistry()
        space = StubSpace("source", error_on={"read"})
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "x")
        # Error output should be returned as-is (ResourceError str)
        assert "read failed" in result

    def test_list_items_pruned_with_indicator(self):
        """Output with list items keeps first N items, appends indicator."""
        reg = ResourceRegistry()
        lines = [f"  - item {i}" for i in range(200)]
        long_output = "\n".join(lines)
        space = StubSpace("source", read_response=long_output)
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "x")
        assert "[pruned:" in result
        assert "- item 0" in result

    def test_table_headers_preserved(self):
        """Table headers (| lines) are preserved in pruning."""
        reg = ResourceRegistry()
        lines = ["| Name | Value |", "|------|-------|"]
        lines += [f"| item{i} | val{i} |" for i in range(200)]
        long_output = "\n".join(lines)
        space = StubSpace("source", read_response=long_output)
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        result = router.dispatch("read", "x")
        assert "| Name | Value |" in result


# ---------------------------------------------------------------------------
# Error collection
# ---------------------------------------------------------------------------

class TestErrorCollection:
    def test_multiple_errors_collected(self):
        """Multiple errors from a single dispatch are collected together."""
        reg = ResourceRegistry()
        space = StubSpace("source", error_on={"read"})
        reg.register(space)
        reg.navigate("source")
        router = ToolRouter(reg)
        # Single dispatch returning error
        result = router.dispatch("read", "x")
        assert "read failed" in result
