"""Tests for bae/agent.py -- core agent loop and helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bae.agent import _agent_namespace, agent_loop, extract_executable
from bae.lm import AgenticBackend


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


# --- AgenticBackend ---


class TestAgenticBackend:
    """Tests for AgenticBackend LM implementation."""

    @pytest.mark.asyncio
    async def test_delegates_choose_type(self):
        """choose_type delegates to wrapped ClaudeCLIBackend."""
        backend = AgenticBackend()
        sentinel = MagicMock()
        backend._cli = MagicMock()
        backend._cli.choose_type = AsyncMock(return_value=sentinel)

        result = await backend.choose_type(["A", "B"], {"ctx": "val"})

        backend._cli.choose_type.assert_called_once_with(["A", "B"], {"ctx": "val"})
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_delegates_make(self):
        """make delegates to wrapped ClaudeCLIBackend."""
        backend = AgenticBackend()
        sentinel = MagicMock()
        backend._cli = MagicMock()
        backend._cli.make = AsyncMock(return_value=sentinel)

        node = MagicMock()
        target = MagicMock()
        result = await backend.make(node, target)

        backend._cli.make.assert_called_once_with(node, target)
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_delegates_decide(self):
        """decide delegates to wrapped ClaudeCLIBackend."""
        backend = AgenticBackend()
        sentinel = MagicMock()
        backend._cli = MagicMock()
        backend._cli.decide = AsyncMock(return_value=sentinel)

        node = MagicMock()
        result = await backend.decide(node)

        backend._cli.decide.assert_called_once_with(node)
        assert result is sentinel

    @pytest.mark.asyncio
    async def test_fill_two_phase(self):
        """fill calls agent_loop for research, then structured extraction."""
        from bae.node import Node

        class TestTarget(Node):
            answer: str

            async def __call__(self) -> None:
                ...

        backend = AgenticBackend(max_iters=3)
        backend._cli = MagicMock()
        backend._cli._run_cli_json = AsyncMock(return_value={"answer": "42"})

        with patch("bae.agent.agent_loop", new_callable=AsyncMock) as mock_loop:
            mock_loop.return_value = "The answer is 42 based on research."
            result = await backend.fill(TestTarget, {}, "TestTarget")

        # agent_loop was called for research phase
        mock_loop.assert_called_once()
        call_kwargs = mock_loop.call_args
        assert call_kwargs.kwargs["max_iters"] == 3

        # Structured extraction was called for extraction phase
        backend._cli._run_cli_json.assert_called_once()
        extract_prompt = backend._cli._run_cli_json.call_args[0][0]
        assert "research" in extract_prompt.lower()

        # Result is a constructed TestTarget
        assert isinstance(result, TestTarget)
        assert result.answer == "42"

    def test_import_from_bae(self):
        """AgenticBackend is importable from bae top-level."""
        from bae import AgenticBackend as AB
        assert AB is AgenticBackend
