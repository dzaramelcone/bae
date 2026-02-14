"""Tests for async_exec expression capture and stdout behavior."""

from __future__ import annotations

import asyncio

import pytest

from bae.repl.exec import async_exec


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
