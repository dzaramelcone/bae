"""Tests for SourceResourcespace: protocol, path resolution, safety, read, enter/nav, glob, grep."""

from pathlib import Path

import pytest

from bae.repl.resource import ResourceError, Resourcespace
from bae.repl.source import SourceResourcespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def src():
    return SourceResourcespace(PROJECT_ROOT)


# --- Protocol conformance ---


class TestProtocol:
    def test_isinstance_resourcespace(self, src):
        assert isinstance(src, Resourcespace)

    def test_supported_tools(self, src):
        assert src.supported_tools() == {"read", "write", "edit", "glob", "grep"}

    def test_children_keys(self, src):
        kids = src.children()
        assert set(kids.keys()) == {"meta", "deps", "config", "tests"}


# --- Module path resolution ---


class TestPathResolution:
    def test_module_to_path_file(self, src):
        from bae.repl.source import _module_to_path

        result = _module_to_path(PROJECT_ROOT, "bae.repl.resource")
        assert result == PROJECT_ROOT / "bae" / "repl" / "resource.py"

    def test_module_to_path_package(self, src):
        from bae.repl.source import _module_to_path

        result = _module_to_path(PROJECT_ROOT, "bae.repl")
        assert result == PROJECT_ROOT / "bae" / "repl" / "__init__.py"

    def test_module_to_path_nonexistent(self, src):
        from bae.repl.source import _module_to_path

        with pytest.raises(ResourceError):
            _module_to_path(PROJECT_ROOT, "bae.nonexistent")

    def test_path_to_module_file(self, src):
        from bae.repl.source import _path_to_module

        result = _path_to_module(PROJECT_ROOT, PROJECT_ROOT / "bae" / "repl" / "resource.py")
        assert result == "bae.repl.resource"

    def test_path_to_module_init(self, src):
        from bae.repl.source import _path_to_module

        result = _path_to_module(PROJECT_ROOT, PROJECT_ROOT / "bae" / "repl" / "__init__.py")
        assert result == "bae.repl"


# --- Path safety ---


class TestPathSafety:
    def test_valid_module_path(self):
        from bae.repl.source import _validate_module_path

        _validate_module_path("bae.repl.resource")  # no exception

    def test_traversal_rejected(self):
        from bae.repl.source import _validate_module_path

        with pytest.raises(ResourceError):
            _validate_module_path("../etc/passwd")

    def test_absolute_path_rejected(self):
        from bae.repl.source import _validate_module_path

        with pytest.raises(ResourceError):
            _validate_module_path("/absolute/path")

    def test_empty_segment_rejected(self):
        from bae.repl.source import _validate_module_path

        with pytest.raises(ResourceError):
            _validate_module_path("bae..repl")


# --- Read operations ---


class TestRead:
    def test_read_root_lists_packages(self, src):
        result = src.read("")
        # Should list top-level packages with docstring + counts
        assert "bae" in result

    def test_read_module_summary(self, src):
        result = src.read("bae.repl.resource")
        # Summary format: module path, docstring line, class count, function count
        assert "bae.repl.resource" in result
        assert "class" in result.lower()
        assert "function" in result.lower()

    def test_read_symbol_source(self, src):
        result = src.read("bae.repl.resource.ResourceError")
        assert "class ResourceError" in result

    def test_read_symbol_isolation(self, src):
        result = src.read("bae.repl.resource.ResourceError")
        # Should NOT contain other classes from the module
        assert "class ResourceRegistry" not in result
        assert "class ResourceHandle" not in result

    def test_read_nonexistent_raises(self, src):
        with pytest.raises(ResourceError):
            src.read("bae.nonexistent")


# --- Enter / Nav ---


class TestEnterNav:
    def test_enter_lists_subresources(self, src):
        result = src.enter()
        assert "source" in result.lower() or "Source" in result
        for sub in ("deps", "config", "tests", "meta"):
            assert sub in result

    def test_nav_lists_packages(self, src):
        result = src.nav()
        assert "bae" in result

    def test_children_match_expected(self, src):
        kids = src.children()
        assert set(kids.keys()) == {"meta", "deps", "config", "tests"}
        for child in kids.values():
            assert isinstance(child, Resourcespace)


# --- Glob ---


class TestGlob:
    def test_glob_wildcard_returns_modules(self, src):
        result = src.glob("bae.repl.*")
        # Should find modules like bae.repl.ai, bae.repl.shell, etc.
        assert "bae.repl.ai" in result
        assert "bae.repl.shell" in result

    def test_glob_exact_match(self, src):
        result = src.glob("bae.repl.resource")
        assert "bae.repl.resource" in result

    def test_glob_nonexistent_no_matches(self, src):
        result = src.glob("bae.nonexistent.*")
        assert result == "(no matches)"

    def test_glob_no_filesystem_paths(self, src):
        result = src.glob("bae.repl.*")
        assert "/" not in result

    def test_glob_budget_overflow_raises(self, src):
        # Globbing a huge pattern should raise ResourceError with narrowing hint
        # if output exceeds CHAR_CAP
        result = src.glob("bae.*")
        # Either fits in budget (string) or raises ResourceError
        if isinstance(result, str) and len(result) > 2000:
            pytest.fail("Glob output exceeded CHAR_CAP without raising ResourceError")


# --- Grep ---


class TestGrep:
    def test_grep_finds_matches(self, src):
        result = src.grep("ResourceError")
        # Should find in bae.repl.resource with module:line: format
        assert "bae.repl.resource:" in result

    def test_grep_scoped_to_module(self, src):
        result = src.grep("ResourceError", "bae.repl.resource")
        assert "bae.repl.resource:" in result
        # Should NOT contain results from other modules
        lines = result.strip().splitlines()
        for line in lines:
            if ":" in line:
                assert line.startswith("bae.repl.resource:")

    def test_grep_no_matches(self, src):
        result = src.grep("zzzznonexistent")
        assert result == "(no matches)"

    def test_grep_no_filesystem_paths(self, src):
        result = src.grep("ResourceError")
        assert "/" not in result

    def test_grep_budget_overflow_raises(self, src):
        # Grepping a very common pattern should raise ResourceError or truncate
        # with narrowing hint if too many matches
        result = src.grep("def ")
        # Either fits in budget or raises ResourceError
        if isinstance(result, str) and len(result) > 2000:
            pytest.fail("Grep output exceeded CHAR_CAP without raising ResourceError")
