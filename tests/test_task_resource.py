"""Integration tests for TaskRoom protocol, tools, navigation, and homespace count."""

from __future__ import annotations

import time

import pytest

from bae.repl.spaces.tasks import TaskRoom
from bae.repl.spaces.tasks.models import TaskStore
from bae.repl.spaces.view import (
    ResourceError,
    ResourceHandle,
    ResourceRegistry,
    Room,
)


MAJOR_BODY = (
    "<assumptions>assume things</assumptions>\n"
    "<reasoning>reason about it</reasoning>\n"
    "<background_research>researched</background_research>\n"
    "<acceptance_criteria>criteria here</acceptance_criteria>"
)

COMPLETE_BODY = (
    MAJOR_BODY + "\n"
    "<outcome>it worked</outcome>\n"
    "<confidence>high</confidence>\n"
    "<retrospective>went well</retrospective>"
)


@pytest.fixture()
def rs(tmp_path):
    return TaskRoom(tmp_path / "tasks.db")


@pytest.fixture()
def registry_ns(tmp_path):
    """Registry with namespace dict and registered TaskRoom."""
    ns = {}
    reg = ResourceRegistry(namespace=ns)
    rs = TaskRoom(tmp_path / "tasks.db")
    reg.register(rs)
    ns["tasks"] = ResourceHandle("tasks", reg)
    return reg, ns, rs


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_is_room(self, rs):
        assert isinstance(rs, Room)

    def test_name(self, rs):
        assert rs.name == "tasks"

    def test_description_non_empty(self, rs):
        assert rs.description

    def test_supported_tools(self, rs):
        assert rs.supported_tools() == {"read", "write", "edit", "glob", "grep"}

    def test_children_empty(self, rs):
        assert rs.children() == {}

    def test_tools_returns_all_callables(self, rs):
        tools = rs.tools()
        assert set(tools.keys()) == {"read", "write", "edit", "glob", "grep"}
        for fn in tools.values():
            assert callable(fn)


# ---------------------------------------------------------------------------
# Entry display
# ---------------------------------------------------------------------------

class TestEntry:
    def test_enter_shows_status_counts(self, rs):
        result = rs.enter()
        assert "open:" in result
        assert "in_progress:" in result
        assert "blocked:" in result

    def test_enter_with_no_tasks_shows_zero(self, rs):
        result = rs.enter()
        assert "open: 0" in result

    def test_enter_shows_stale_warning(self, tmp_path):
        rs = TaskRoom(tmp_path / "tasks.db")
        task = rs._store.create("stale task", MAJOR_BODY, priority=(1, 0, 0))
        old_time = time.time() - (15 * 86400)
        rs._store._conn.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            (old_time, int(task["id"])),
        )
        rs._store._conn.commit()
        result = rs.enter()
        assert "Stale" in result
        assert "14+" in result or "14" in result


# ---------------------------------------------------------------------------
# Navigation via ResourceRegistry (TSK-01)
# ---------------------------------------------------------------------------

class TestNavigation:
    def test_navigate_to_tasks(self, registry_ns):
        reg, ns, _ = registry_ns
        result = reg.navigate("tasks")
        assert "home > tasks" in result
        assert "Tool" in result  # functions table header

    def test_tools_injected_into_namespace(self, registry_ns):
        reg, ns, _ = registry_ns
        reg.navigate("tasks")
        for tool in ("read", "write", "edit", "glob", "grep"):
            assert tool in ns, f"{tool} not in namespace"
            assert callable(ns[tool])

    def test_tools_removed_on_navigate_away(self, registry_ns):
        reg, ns, rs = registry_ns
        class StubSpace:
            name = "stub"
            description = "stub"
            def enter(self) -> str: return "stub"
            def nav(self) -> str: return ""
            def read(self, target: str = "") -> str: return ""
            def supported_tools(self) -> set[str]: return {"read"}
            def children(self) -> dict: return {}
            def tools(self) -> dict: return {"read": self.read}

        reg.register(StubSpace())
        reg.navigate("tasks")
        assert "write" in ns
        reg.navigate("stub")
        assert "write" not in ns
        assert "edit" not in ns
        assert "glob" not in ns
        assert "grep" not in ns


# ---------------------------------------------------------------------------
# Tool: write (TSK-02)
# ---------------------------------------------------------------------------

class TestWrite:
    def test_write_creates_task(self, rs):
        result = rs.write("Deploy service", MAJOR_BODY, priority="1.0.0")
        assert "Created task" in result
        assert "Deploy service" in result

    def test_write_major_enforces_sections(self, rs):
        with pytest.raises(ResourceError, match="structured sections"):
            rs.write("Bad major", "no sections here", priority="1.0.0")

    def test_write_minor_links_to_parent(self, rs):
        rs.write("Parent task", MAJOR_BODY, priority="1.0.0")
        result = rs.write("Subtask", "sub body", priority="1.1.0")
        assert "Created task" in result

    def test_write_new_tag_shows_friction(self, rs):
        rs.write("First", MAJOR_BODY, priority="1.0.0", tags="existing")
        result = rs.write("Second", MAJOR_BODY, priority="2.0.0", tags="brand_new")
        assert "New tag" in result
        assert "Existing tags" in result

    def test_write_zero_priority_skips_major_validation(self, rs):
        result = rs.write("Quick note")
        assert "Created task" in result


# ---------------------------------------------------------------------------
# Tool: read (TSK-03)
# ---------------------------------------------------------------------------

class TestRead:
    def test_read_no_args_lists_active(self, rs):
        rs.write("Task A", MAJOR_BODY, priority="1.0.0")
        result = rs.read()
        assert "Active tasks" in result
        assert "Task A" in result

    def test_read_task_id(self, rs):
        rs.write("Readable", MAJOR_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        result = rs.read(task_id)
        assert "Readable" in result
        assert task_id in result

    def test_read_status_filter(self, rs):
        rs.write("Blocked one", MAJOR_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        rs._store.update(tasks[0]["id"], status="blocked")
        result = rs.read("status:blocked")
        assert "Blocked one" in result

    def test_read_tag_filter(self, rs):
        rs.write("Tagged", MAJOR_BODY, priority="1.0.0", tags="urgent")
        result = rs.read("tag:urgent")
        assert "Tagged" in result

    def test_read_bad_target(self, rs):
        with pytest.raises(ResourceError, match="not found"):
            rs.read("zzzzzz")


# ---------------------------------------------------------------------------
# Tool: edit (TSK-04, TSK-05)
# ---------------------------------------------------------------------------

class TestEdit:
    def test_edit_status(self, rs):
        rs.write("Update me", MAJOR_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        result = rs.edit(task_id, status="in_progress")
        assert "Updated" in result
        assert "PROG" in result

    def test_edit_done_task_raises(self, rs):
        rs.write("Final task", COMPLETE_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        rs._store.mark_done(task_id)
        with pytest.raises(ResourceError, match="final"):
            rs.edit(task_id, status="open")

    def test_edit_positional_id_keyword_status(self, rs):
        """Regression: edit('id', status='in_progress') must work."""
        rs.write("Positional test", MAJOR_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        result = rs.edit(task_id, status="in_progress")
        assert "Updated" in result

    def test_edit_status_done_uses_lifecycle(self, rs):
        """edit(id, status='done') goes through mark_done lifecycle."""
        rs.write("Lifecycle test", COMPLETE_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        result = rs.edit(task_id, status="done")
        assert "Updated" in result
        assert "DONE" in result

    def test_edit_status_done_zero_priority(self, rs):
        """edit(id, status='done') works for unclassified (0.0.0) tasks."""
        rs.write("Quick task")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        result = rs.edit(task_id, status="done")
        assert "DONE" in result

    def test_dispatch_edit_with_kwargs(self, registry_ns):
        """Regression: ToolRouter dispatches edit with kwargs correctly."""
        reg, ns, rs = registry_ns
        reg.navigate("tasks")
        rs.write("Dispatch test", MAJOR_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        from bae.repl.tools import ToolRouter
        router = ToolRouter(reg)
        result = router.dispatch("edit", task_id, status="in_progress")
        assert "Updated" in result


# ---------------------------------------------------------------------------
# Tool: glob
# ---------------------------------------------------------------------------

class TestGlob:
    def test_glob_matches_title(self, rs):
        rs.write("Deploy service")
        rs.write("Deploy database")
        rs.write("Fix login bug")
        result = rs.glob("Deploy*")
        assert "Deploy service" in result
        assert "Deploy database" in result
        assert "Fix login" not in result

    def test_glob_no_match(self, rs):
        rs.write("Something")
        result = rs.glob("zzz*")
        assert "No tasks" in result

    def test_glob_case_insensitive(self, rs):
        rs.write("Deploy Service")
        result = rs.glob("deploy*")
        assert "Deploy Service" in result


# ---------------------------------------------------------------------------
# Tool: grep (TSK-06)
# ---------------------------------------------------------------------------

class TestGrep:
    def test_grep_finds_tasks(self, rs):
        rs.write("Deploy kubernetes", MAJOR_BODY, priority="1.0.0")
        result = rs.grep("kubernetes")
        assert "kubernetes" in result.lower()
        assert "1 result" in result

    def test_grep_no_results_with_hints(self, rs):
        rs.write("Something", MAJOR_BODY, priority="1.0.0")
        result = rs.grep("nonexistent_xyzzy")
        assert "No results" in result
        assert "read()" in result or "keywords" in result


# ---------------------------------------------------------------------------
# Persistence (TSK-07)
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_data_survives_new_instance(self, tmp_path):
        db_path = tmp_path / "tasks.db"
        rs1 = TaskRoom(db_path)
        rs1.write("Persistent task", MAJOR_BODY, priority="1.0.0")
        rs2 = TaskRoom(db_path)
        result = rs2.read()
        assert "Persistent task" in result


# ---------------------------------------------------------------------------
# Homespace count (TSK-08)
# ---------------------------------------------------------------------------

class TestHomespaceCount:
    def test_orientation_shows_status_counts(self, tmp_path):
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        rs = TaskRoom(tmp_path / "tasks.db")
        reg.register(rs)
        rs.write("Outstanding task", MAJOR_BODY, priority="1.0.0")
        result = reg.home()
        assert "open: 1" in result
        assert "Start here" in result

    def test_orientation_no_start_here_when_zero(self, tmp_path):
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        rs = TaskRoom(tmp_path / "tasks.db")
        reg.register(rs)
        result = reg.home()
        assert "open: 0" in result
        assert "Start here" not in result
