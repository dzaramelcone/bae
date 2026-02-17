"""Tests for TaskStore CRUD, FTS5 search, priority ordering, lifecycle, and custom tool cleanup."""

from __future__ import annotations

import time

import pytest

from bae.repl.spaces.tasks.models import TaskStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.db")


def _minor_task(store, major=1, minor=1, title="subtask"):
    """Create a minor task after creating its parent major task."""
    store.create("major", MAJOR_BODY, priority=(major, 0, 0))
    return store.create(title, "minor body", priority=(major, minor, 0))


# ---------------------------------------------------------------------------
# Schema and initialization
# ---------------------------------------------------------------------------

class TestSchema:
    def test_creates_database_file(self, tmp_path):
        db = tmp_path / "tasks.db"
        TaskStore(db)
        assert db.exists()

    def test_creates_all_tables(self, store):
        tables = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {row["name"] for row in tables}
        assert "tasks" in names
        assert "task_tags" in names
        assert "task_dependencies" in names
        assert "task_audit" in names

    def test_wal_mode_enabled(self, store):
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"


# ---------------------------------------------------------------------------
# CRUD basics
# ---------------------------------------------------------------------------

class TestCRUD:
    def test_create_returns_dict_with_all_fields(self, store):
        task = store.create("test task", MAJOR_BODY, priority=(1, 0, 0))
        assert task["title"] == "test task"
        assert task["body"] == MAJOR_BODY
        assert task["status"] == "open"
        assert task["priority_major"] == 1
        assert task["priority_minor"] == 0
        assert task["priority_patch"] == 0
        assert task["id"]
        assert task["created_at"] > 0
        assert task["updated_at"] > 0
        assert task["tags"] == []

    def test_get_retrieves_by_id(self, store):
        created = store.create("find me", MAJOR_BODY, priority=(1, 0, 0))
        found = store.get(created["id"])
        assert found["title"] == "find me"

    def test_get_raises_for_missing(self, store):
        with pytest.raises(ValueError, match="not found"):
            store.get("zzzzzz")

    def test_get_includes_tags(self, store):
        task = store.create("tagged", MAJOR_BODY, priority=(1, 0, 0))
        store.add_tag(task["id"], "urgent")
        found = store.get(task["id"])
        assert "urgent" in found["tags"]

    def test_list_active_excludes_done_cancelled(self, store):
        t1 = store.create("active", MAJOR_BODY, priority=(1, 0, 0))
        t2 = store.create("also active", MAJOR_BODY, priority=(2, 0, 0))
        store.update(t1["id"], body=COMPLETE_BODY)
        store.mark_done(t1["id"])
        active = store.list_active()
        ids = [t["id"] for t in active]
        assert t1["id"] not in ids
        assert t2["id"] in ids

    def test_list_active_orders_by_status_then_priority(self, store):
        t_open = store.create("open task", MAJOR_BODY, priority=(2, 0, 0))
        t_ip = store.create("in progress", MAJOR_BODY, priority=(3, 0, 0))
        store.update(t_ip["id"], status="in_progress")
        active = store.list_active()
        # in_progress should come first despite higher priority number
        assert active[0]["id"] == t_ip["id"]
        assert active[1]["id"] == t_open["id"]


# ---------------------------------------------------------------------------
# Priority and hierarchy
# ---------------------------------------------------------------------------

class TestPriority:
    def test_tasks_sort_by_priority_tuple(self, store):
        store.create("low", MAJOR_BODY, priority=(3, 0, 0))
        store.create("high", MAJOR_BODY, priority=(1, 0, 0))
        store.create("mid", MAJOR_BODY, priority=(2, 0, 0))
        tasks = store.list_active()
        priorities = [(t["priority_major"], t["priority_minor"], t["priority_patch"]) for t in tasks]
        assert priorities == sorted(priorities)

    def test_minor_task_validates_parent_exists(self, store):
        store.create("parent", MAJOR_BODY, priority=(1, 0, 0))
        child = store.create("child", "child body", priority=(1, 1, 0))
        assert child["parent_id"] is not None

    def test_minor_task_fails_without_parent(self, store):
        with pytest.raises(ValueError, match="No major task found"):
            store.create("orphan", "body", priority=(99, 1, 0))

    def test_major_task_body_must_have_sections(self, store):
        with pytest.raises(ValueError, match="must contain"):
            store.create("bad major", "no sections", priority=(1, 0, 0))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_open_to_in_progress_to_done(self, store):
        task = store.create("lifecycle", MAJOR_BODY, priority=(1, 0, 0))
        assert task["status"] == "open"
        updated = store.update(task["id"], status="in_progress")
        assert updated["status"] == "in_progress"
        store.update(task["id"], body=COMPLETE_BODY)
        done = store.mark_done(task["id"])
        assert done["status"] == "done"

    def test_done_is_final(self, store):
        task = store.create("final", MAJOR_BODY, priority=(1, 0, 0))
        store.update(task["id"], body=COMPLETE_BODY)
        store.mark_done(task["id"])
        with pytest.raises(ValueError, match="final"):
            store.update(task["id"], status="open")

    def test_cancelled_is_final(self, store):
        task = store.create("cancel me", MAJOR_BODY, priority=(1, 0, 0))
        store.cancel(task["id"])
        with pytest.raises(ValueError, match="final"):
            store.update(task["id"], status="open")

    def test_mark_done_returns_user_gated_flag(self, store):
        task = store.create("gated", MAJOR_BODY, priority=(1, 0, 0), user_gated=True)
        store.update(task["id"], body=COMPLETE_BODY)
        result = store.mark_done(task["id"])
        assert result.get("_user_gated") is True

    def test_cancel_transitions(self, store):
        task = store.create("cancel", MAJOR_BODY, priority=(1, 0, 0))
        result = store.cancel(task["id"])
        assert result["status"] == "cancelled"

    def test_mark_done_checks_completion_sections(self, store):
        task = store.create("incomplete", MAJOR_BODY, priority=(1, 0, 0))
        with pytest.raises(ValueError, match="completion sections"):
            store.mark_done(task["id"])


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

class TestTags:
    def test_add_and_remove_tag(self, store):
        task = store.create("tagged", MAJOR_BODY, priority=(1, 0, 0))
        store.add_tag(task["id"], "feature")
        assert "feature" in store.get(task["id"])["tags"]
        store.remove_tag(task["id"], "feature")
        assert "feature" not in store.get(task["id"])["tags"]

    def test_all_tags_returns_distinct(self, store):
        t1 = store.create("a", MAJOR_BODY, priority=(1, 0, 0))
        t2 = store.create("b", MAJOR_BODY, priority=(2, 0, 0))
        store.add_tag(t1["id"], "bug")
        store.add_tag(t2["id"], "bug")
        store.add_tag(t2["id"], "feature")
        assert store.all_tags() == {"bug", "feature"}

    def test_list_active_with_tag_filter(self, store):
        t1 = store.create("has tag", MAJOR_BODY, priority=(1, 0, 0))
        store.create("no tag", MAJOR_BODY, priority=(2, 0, 0))
        store.add_tag(t1["id"], "urgent")
        filtered = store.list_active(tag_filter=["urgent"])
        assert len(filtered) == 1
        assert filtered[0]["id"] == t1["id"]


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

class TestDependencies:
    def test_add_dependency_sets_blocked(self, store):
        t1 = store.create("blocker", MAJOR_BODY, priority=(1, 0, 0))
        t2 = store.create("blocked", MAJOR_BODY, priority=(2, 0, 0))
        store.add_dependency(t2["id"], t1["id"])
        assert store.get(t2["id"])["status"] == "blocked"

    def test_remove_dependency_unblocks(self, store):
        t1 = store.create("blocker", MAJOR_BODY, priority=(1, 0, 0))
        t2 = store.create("blocked", MAJOR_BODY, priority=(2, 0, 0))
        store.add_dependency(t2["id"], t1["id"])
        store.remove_dependency(t2["id"], t1["id"])
        assert store.get(t2["id"])["status"] == "open"

    def test_cycle_detection(self, store):
        t1 = store.create("a", MAJOR_BODY, priority=(1, 0, 0))
        t2 = store.create("b", MAJOR_BODY, priority=(2, 0, 0))
        store.add_dependency(t2["id"], t1["id"])
        with pytest.raises(ValueError, match="Cycle detected"):
            store.add_dependency(t1["id"], t2["id"])

    def test_mark_done_blocked_by_unfinished(self, store):
        t1 = store.create("blocker", MAJOR_BODY, priority=(1, 0, 0))
        t2 = store.create("blocked", MAJOR_BODY, priority=(2, 0, 0))
        store.add_dependency(t2["id"], t1["id"])
        store.update(t2["id"], body=COMPLETE_BODY)
        with pytest.raises(ValueError, match="blocked by"):
            store.mark_done(t2["id"])


# ---------------------------------------------------------------------------
# FTS search
# ---------------------------------------------------------------------------

class TestFTSSearch:
    def test_search_finds_by_title(self, store):
        store.create("deploy kubernetes", MAJOR_BODY, priority=(1, 0, 0))
        store.create("write docs", MAJOR_BODY, priority=(2, 0, 0))
        results = store.search("kubernetes")
        assert len(results) == 1
        assert results[0]["title"] == "deploy kubernetes"

    def test_search_finds_by_body(self, store):
        body = MAJOR_BODY + "\nThis task involves database migration."
        store.create("generic title", body, priority=(1, 0, 0))
        results = store.search("migration")
        assert len(results) == 1

    def test_search_returns_bm25_ordered(self, store):
        store.create("kubernetes deploy", MAJOR_BODY + "\nkubernetes kubernetes kubernetes", priority=(1, 0, 0))
        store.create("unrelated", MAJOR_BODY, priority=(2, 0, 0))
        results = store.search("kubernetes")
        assert len(results) == 1  # only the matching one
        assert results[0]["title"] == "kubernetes deploy"

    def test_search_no_matches_returns_empty(self, store):
        store.create("something", MAJOR_BODY, priority=(1, 0, 0))
        assert store.search("nonexistent_xyzzy") == []


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class TestAudit:
    def test_status_change_logged(self, store):
        task = store.create("audit me", MAJOR_BODY, priority=(1, 0, 0))
        store.update(task["id"], status="in_progress")
        audits = store._conn.execute(
            "SELECT * FROM task_audit WHERE task_id = ?", (int(task["id"]),)
        ).fetchall()
        fields = [a["field"] for a in audits]
        assert "status" in fields

    def test_field_update_logged(self, store):
        task = store.create("audit field", MAJOR_BODY, priority=(1, 0, 0))
        store.update(task["id"], title="new title")
        audits = store._conn.execute(
            "SELECT * FROM task_audit WHERE task_id = ? AND field = 'title'",
            (int(task["id"]),),
        ).fetchall()
        assert len(audits) == 1
        assert audits[0]["old_value"] == "audit field"
        assert audits[0]["new_value"] == "new title"


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------

class TestCounts:
    def test_status_counts(self, store):
        store.create("a", MAJOR_BODY, priority=(1, 0, 0))
        store.create("b", MAJOR_BODY, priority=(2, 0, 0))
        t3 = store.create("c", MAJOR_BODY, priority=(3, 0, 0))
        store.update(t3["id"], status="in_progress")
        counts = store.status_counts()
        assert counts["open"] == 2
        assert counts["in_progress"] == 1

    def test_outstanding_count(self, store):
        store.create("a", MAJOR_BODY, priority=(1, 0, 0))
        store.create("b", MAJOR_BODY, priority=(2, 0, 0))
        assert store.outstanding_count() == 2

    def test_stale_tasks(self, store):
        task = store.create("stale", MAJOR_BODY, priority=(1, 0, 0))
        # Manually backdate updated_at
        old_time = time.time() - (15 * 86400)
        store._conn.execute(
            "UPDATE tasks SET updated_at = ? WHERE id = ?",
            (old_time, int(task["id"])),
        )
        store._conn.commit()
        stale = store.stale_tasks(days=14)
        assert len(stale) == 1
        assert stale[0]["id"] == task["id"]


# ---------------------------------------------------------------------------
# Custom tool cleanup (view.py change)
# ---------------------------------------------------------------------------

class TestCustomToolCleanup:
    def test_custom_tools_removed_on_navigation_away(self):
        from bae.repl.spaces.view import ResourceRegistry

        ns = {}
        reg = ResourceRegistry(namespace=ns)

        class SpaceWithCustom:
            name = "tasks"
            description = "task management"
            def enter(self) -> str: return self.description
            def nav(self) -> str: return ""
            def read(self, target: str = "") -> str: return ""
            def supported_tools(self) -> set[str]: return {"read", "add"}
            def children(self) -> dict: return {}
            def tools(self) -> dict:
                return {"read": self.read, "add": lambda title: f"added {title}"}

        class PlainSpace:
            name = "source"
            description = "source code"
            def enter(self) -> str: return self.description
            def nav(self) -> str: return ""
            def read(self, target: str = "") -> str: return ""
            def supported_tools(self) -> set[str]: return {"read"}
            def children(self) -> dict: return {}
            def tools(self) -> dict:
                return {"read": self.read}

        reg.register(SpaceWithCustom())
        reg.register(PlainSpace())

        reg.navigate("tasks")
        assert "add" in ns
        assert callable(ns["add"])

        reg.navigate("source")
        assert "add" not in ns
        assert "read" in ns
