"""Tests for bae/agent.py -- core agent loop and helpers."""

from __future__ import annotations

import asyncio

import pytest

from bae.agent import _agent_namespace, agent_loop, extract_executable


# --- extract_executable ---


def test_extract_executable_single_block():
    text = "Here is code:\n<run>\nprint('hello')\n</run>\nDone."
    code, extra = extract_executable(text)
    assert code == "print('hello')"
    assert extra == 0


def test_extract_executable_multiple_blocks():
    text = (
        "<run>\nfirst()\n</run>\n"
        "some text\n"
        "<run>\nsecond()\n</run>\n"
        "<run>\nthird()\n</run>"
    )
    code, extra = extract_executable(text)
    assert code == "first()"
    assert extra == 2


def test_extract_executable_no_blocks():
    text = "Just plain text, no code blocks here."
    code, extra = extract_executable(text)
    assert code is None
    assert extra == 0


# --- agent_loop ---


@pytest.mark.asyncio
async def test_agent_loop_no_code():
    """send returns plain text -- loop exits immediately."""
    async def send(prompt):
        return "Just a plain answer, no code."

    ns = _agent_namespace()
    result = await agent_loop("question?", send=send, namespace=ns)
    assert result == "Just a plain answer, no code."


@pytest.mark.asyncio
async def test_agent_loop_single_iteration():
    """send returns <run> block first, then plain text."""
    calls = []

    async def send(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return "<run>\nprint('hi')\n</run>"
        return "Done, here is the answer."

    ns = _agent_namespace()
    result = await agent_loop("do stuff", send=send, namespace=ns)
    assert result == "Done, here is the answer."
    assert len(calls) == 2
    # Second call should contain the output from print('hi')
    assert "hi" in calls[1]


@pytest.mark.asyncio
async def test_agent_loop_max_iters():
    """send always returns code blocks -- loop stops at max_iters."""
    async def send(prompt):
        return "<run>\nx = 1\n</run>"

    ns = _agent_namespace()
    result = await agent_loop(
        "go", send=send, namespace=ns, max_iters=3,
    )
    # Should have stopped after 3 iterations
    assert "<run>" in result


@pytest.mark.asyncio
async def test_agent_loop_execution_error():
    """Code that raises feeds traceback back to send."""
    calls = []

    async def send(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return "<run>\nraise ValueError('boom')\n</run>"
        return "I see the error."

    ns = _agent_namespace()
    result = await agent_loop("try this", send=send, namespace=ns)
    assert result == "I see the error."
    assert len(calls) == 2
    assert "ValueError" in calls[1]
    assert "boom" in calls[1]


# --- _agent_namespace ---


def test_agent_namespace_fresh():
    """Verify _agent_namespace returns dict with expected keys, no shared state."""
    ns1 = _agent_namespace()
    ns2 = _agent_namespace()

    # Expected keys present
    for key in ("__builtins__", "json", "re", "os", "Path"):
        assert key in ns1, f"Missing key: {key}"

    # Fresh dicts -- no shared state
    ns1["_test_marker"] = True
    assert "_test_marker" not in ns2
