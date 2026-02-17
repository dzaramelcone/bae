"""Integration tests for TaskResourcespace protocol, tools, navigation, and homespace count."""

from __future__ import annotations

import time

import pytest

from bae.repl.spaces.tasks import TaskResourcespace
from bae.repl.spaces.tasks.models import TaskStore, from_base36
from bae.repl.spaces.view import (
    ResourceError,
    ResourceHandle,
    ResourceRegistry,
    Resourcespace,
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
    return TaskResourcespace(tmp_path / "tasks.db")


@pytest.fixture()
def registry_ns(tmp_path):
    """Registry with namespace dict and registered TaskResourcespace."""
    ns = {}
    reg = ResourceRegistry(namespace=ns)
    rs = TaskResourcespace(tmp_path / "tasks.db")
    reg.register(rs)
    ns["tasks"] = ResourceHandle("tasks", reg)
    return reg, ns, rs


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestProtocol:
    def test_is_resourcespace(self, rs):
        assert isinstance(rs, Resourcespace)

    def test_name(self, rs):
        assert rs.name == "tasks"

    def test_description_non_empty(self, rs):
        assert rs.description

    def test_supported_tools(self, rs):
        assert rs.supported_tools() == {"read", "add", "done", "update", "search"}

    def test_children_empty(self, rs):
        assert rs.children() == {}

    def test_tools_returns_all_callables(self, rs):
        tools = rs.tools()
        assert set(tools.keys()) == {"read", "add", "done", "update", "search"}
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
        rs = TaskResourcespace(tmp_path / "tasks.db")
        task = rs._store.create("stale task", MAJOR_BODY, priority=(1, 0, 0))
        old_time = time.time() - (15 * 86400)
        rs._store._conn.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            (old_time, from_base36(task["id"])),
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
        for tool in ("read", "add", "done", "update", "search"):
            assert tool in ns, f"{tool} not in namespace"
            assert callable(ns[tool])

    def test_tools_removed_on_navigate_away(self, registry_ns):
        reg, ns, rs = registry_ns
        # Register a second space to navigate to
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
        assert "add" in ns
        reg.navigate("stub")
        assert "add" not in ns
        assert "done" not in ns
        assert "update" not in ns
        assert "search" not in ns


# ---------------------------------------------------------------------------
# Tool: add (TSK-02)
# ---------------------------------------------------------------------------

class TestAdd:
    def test_add_creates_task(self, rs):
        result = rs.add("Deploy service", MAJOR_BODY, priority="1.0.0")
        assert "Created task" in result
        assert "Deploy service" in result

    def test_add_major_enforces_sections(self, rs):
        with pytest.raises(ResourceError, match="structured sections"):
            rs.add("Bad major", "no sections here", priority="1.0.0")

    def test_add_minor_links_to_parent(self, rs):
        rs.add("Parent task", MAJOR_BODY, priority="1.0.0")
        result = rs.add("Subtask", "sub body", priority="1.1.0")
        assert "Created task" in result

    def test_add_new_tag_shows_friction(self, rs):
        rs.add("First", MAJOR_BODY, priority="1.0.0", tags="existing")
        result = rs.add("Second", MAJOR_BODY, priority="2.0.0", tags="brand_new")
        assert "New tag" in result
        assert "Existing tags" in result

    def test_add_zero_priority_skips_major_validation(self, rs):
        # 0.0.0 is the default, no body sections needed
        result = rs.add("Quick note")
        assert "Created task" in result


# ---------------------------------------------------------------------------
# Tool: read (TSK-03)
# ---------------------------------------------------------------------------

class TestRead:
    def test_read_no_args_lists_active(self, rs):
        rs.add("Task A", MAJOR_BODY, priority="1.0.0")
        result = rs.read()
        assert "Active tasks" in result
        assert "Task A" in result

    def test_read_task_id(self, rs):
        rs.add("Readable", MAJOR_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        result = rs.read(task_id)
        assert "Readable" in result
        assert task_id in result

    def test_read_status_filter(self, rs):
        rs.add("Blocked one", MAJOR_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        rs._store.update(tasks[0]["id"], status="blocked")
        result = rs.read("status:blocked")
        assert "Blocked one" in result

    def test_read_tag_filter(self, rs):
        rs.add("Tagged", MAJOR_BODY, priority="1.0.0", tags="urgent")
        result = rs.read("tag:urgent")
        assert "Tagged" in result

    def test_read_bad_target(self, rs):
        with pytest.raises(ResourceError, match="not found"):
            rs.read("zzzzzz")


# ---------------------------------------------------------------------------
# Tool: done (TSK-05)
# ---------------------------------------------------------------------------

class TestDone:
    def test_done_marks_complete(self, rs):
        rs.add("Finish me", COMPLETE_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        result = rs.done(task_id)
        assert "Done" in result

    def test_done_user_gated_returns_message(self, rs):
        # Create task, then manually set user_gated
        rs.add("Gated task", COMPLETE_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        rs._store.update(task_id, user_gated=1)
        result = rs.done(task_id)
        assert "user-gated" in result.lower() or "Confirm" in result


# ---------------------------------------------------------------------------
# Tool: update (TSK-04)
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_update_status(self, rs):
        rs.add("Update me", MAJOR_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        result = rs.update(task_id, status="in_progress")
        assert "Updated" in result
        assert "status" in result

    def test_update_done_task_raises(self, rs):
        rs.add("Final task", COMPLETE_BODY, priority="1.0.0")
        tasks = rs._store.list_active()
        task_id = tasks[0]["id"]
        rs._store.mark_done(task_id)
        with pytest.raises(ResourceError, match="final"):
            rs.update(task_id, status="open")


# ---------------------------------------------------------------------------
# Tool: search (TSK-06)
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_finds_tasks(self, rs):
        rs.add("Deploy kubernetes", MAJOR_BODY, priority="1.0.0")
        result = rs.search("kubernetes")
        assert "kubernetes" in result.lower()
        assert "1 result" in result

    def test_search_no_results_with_hints(self, rs):
        rs.add("Something", MAJOR_BODY, priority="1.0.0")
        result = rs.search("nonexistent_xyzzy")
        assert "No results" in result
        assert "read()" in result or "keywords" in result


# ---------------------------------------------------------------------------
# Persistence (TSK-07)
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_data_survives_new_instance(self, tmp_path):
        db_path = tmp_path / "tasks.db"
        rs1 = TaskResourcespace(db_path)
        rs1.add("Persistent task", MAJOR_BODY, priority="1.0.0")
        rs2 = TaskResourcespace(db_path)
        result = rs2.read()
        assert "Persistent task" in result


# ---------------------------------------------------------------------------
# Homespace count (TSK-08)
# ---------------------------------------------------------------------------

class TestHomespaceCount:
    def test_orientation_shows_outstanding(self, tmp_path):
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        rs = TaskResourcespace(tmp_path / "tasks.db")
        reg.register(rs)
        rs.add("Outstanding task", MAJOR_BODY, priority="1.0.0")
        result = reg.home()
        assert "Tasks: 1 outstanding" in result

    def test_orientation_omits_when_zero(self, tmp_path):
        ns = {}
        reg = ResourceRegistry(namespace=ns)
        rs = TaskResourcespace(tmp_path / "tasks.db")
        reg.register(rs)
        result = reg.home()
        assert "outstanding" not in result
