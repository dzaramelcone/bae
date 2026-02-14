"""Tests for async_exec expression capture and stdout behavior."""

from __future__ import annotations

import asyncio

import pytest

from bae.repl.exec import async_exec
from bae.repl.shell import _contains_coroutines, _count_and_close_coroutines


@pytest.mark.asyncio
async def test_expr_returns_value():
    ns = {}
    result, stdout = await async_exec("1 + 1", ns)
    assert result == 2
    assert stdout == ""


@pytest.mark.asyncio
async def test_assignment_returns_none():
    ns = {}
    result, stdout = await async_exec("x = 42", ns)
    assert result is None
    assert stdout == ""


@pytest.mark.asyncio
async def test_for_loop_with_underscore_returns_none():
    ns = {}
    result, stdout = await async_exec("for _ in range(20): pass", ns)
    assert result is None
    assert stdout == ""


@pytest.mark.asyncio
async def test_for_loop_with_print_returns_none():
    ns = {}
    result, stdout = await async_exec("for _ in range(5): print(_)", ns)
    assert result is None
    assert stdout == "0\n1\n2\n3\n4\n"


@pytest.mark.asyncio
async def test_await_expr_returns_coroutine():
    """Async expressions return unawaited coroutine for TaskManager tracking.

    The caller (shell._dispatch PY) awaits the coroutine via tm.submit().
    The result is captured in namespace['_'] after the coroutine completes.
    """
    ns = {"asyncio": asyncio}
    result, stdout = await async_exec("await asyncio.sleep(0) or 'done'", ns)
    assert asyncio.iscoroutine(result), f"Expected coroutine, got {type(result)}"
    await result
    assert ns["_"] == "done"
    assert stdout == ""


@pytest.mark.asyncio
async def test_multiline_last_expr():
    ns = {}
    result, stdout = await async_exec("x = 10\nx + 5", ns)
    assert result == 15
    assert stdout == ""


@pytest.mark.asyncio
async def test_multiline_last_statement():
    ns = {}
    result, stdout = await async_exec("x = 10\ny = 20", ns)
    assert result is None
    assert stdout == ""


@pytest.mark.asyncio
async def test_print_captures_stdout():
    result, stdout = await async_exec("print('hello')", {})
    assert result is None
    assert stdout == "hello\n"


# --- _contains_coroutines / _count_and_close_coroutines tests ---


def test_contains_coroutines_single():
    """Single coroutine detected."""
    coro = asyncio.sleep(0)
    assert _contains_coroutines(coro) is True
    coro.close()


def test_contains_coroutines_list():
    """List of coroutines detected."""
    coros = [asyncio.sleep(0), asyncio.sleep(0)]
    assert _contains_coroutines(coros) is True
    for c in coros:
        c.close()


def test_contains_coroutines_nested():
    """Nested lists of coroutines detected."""
    coros = [[asyncio.sleep(0)], [asyncio.sleep(0)]]
    assert _contains_coroutines(coros) is True
    for inner in coros:
        for c in inner:
            c.close()


def test_contains_coroutines_dict():
    """Dict values containing coroutines detected."""
    d = {"a": asyncio.sleep(0), "b": 42}
    assert _contains_coroutines(d) is True
    d["a"].close()


def test_contains_coroutines_plain():
    """Plain values return False."""
    assert _contains_coroutines(42) is False
    assert _contains_coroutines("hello") is False
    assert _contains_coroutines([1, 2, 3]) is False
    assert _contains_coroutines({"a": 1}) is False
    assert _contains_coroutines(None) is False


def test_contains_coroutines_mixed():
    """Mixed list with ints and coroutines detected."""
    coro = asyncio.sleep(0)
    mixed = [1, "text", coro, 3.14]
    assert _contains_coroutines(mixed) is True
    coro.close()


def test_count_and_close_coroutines():
    """Counts coroutines and closes them."""
    coros = [asyncio.sleep(0) for _ in range(5)]
    n = _count_and_close_coroutines(coros)
    assert n == 5
