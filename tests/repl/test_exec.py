"""Tests for async_exec expression capture behavior."""

from __future__ import annotations

import asyncio
from io import StringIO
from unittest.mock import patch

import pytest

from bae.repl.exec import async_exec


@pytest.mark.asyncio
async def test_expr_returns_value():
    ns = {}
    result = await async_exec("1 + 1", ns)
    assert result == 2


@pytest.mark.asyncio
async def test_assignment_returns_none():
    ns = {}
    result = await async_exec("x = 42", ns)
    assert result is None


@pytest.mark.asyncio
async def test_for_loop_with_underscore_returns_none():
    ns = {}
    result = await async_exec("for _ in range(20): pass", ns)
    assert result is None


@pytest.mark.asyncio
async def test_for_loop_with_print_returns_none():
    ns = {}
    buf = StringIO()
    with patch("sys.stdout", buf):
        result = await async_exec("for _ in range(5): print(_)", ns)
    assert result is None
    assert buf.getvalue() == "0\n1\n2\n3\n4\n"


@pytest.mark.asyncio
async def test_await_expr_returns_value():
    ns = {"asyncio": asyncio}
    result = await async_exec("await asyncio.sleep(0) or 'done'", ns)
    assert result == "done"


@pytest.mark.asyncio
async def test_multiline_last_expr():
    ns = {}
    result = await async_exec("x = 10\nx + 5", ns)
    assert result == 15


@pytest.mark.asyncio
async def test_multiline_last_statement():
    ns = {}
    result = await async_exec("x = 10\ny = 20", ns)
    assert result is None
