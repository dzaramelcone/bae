"""Integration tests for AI wiring in CortexShell."""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, patch

import pytest

from bae.lm import ClaudeCLIBackend
from bae.repl.ai import AI
from bae.repl.shell import CortexShell


class TestAIIntegration:
    """Tests verifying AI is wired into CortexShell correctly."""

    def test_ai_in_namespace(self):
        """AI object is accessible in the shell namespace."""
        shell = CortexShell()
        assert "ai" in shell.namespace
        assert isinstance(shell.namespace["ai"], AI)

    def test_ai_repr_in_namespace(self):
        """AI repr shows usage hint and session info."""
        shell = CortexShell()
        r = repr(shell.namespace["ai"])
        assert "await ai('question')" in r
        assert "session " in r

    def test_ai_has_router(self):
        """AI holds same router reference as shell."""
        shell = CortexShell()
        assert shell.ai._router is shell.router

    def test_ai_has_namespace(self):
        """AI holds same namespace reference (sees live state)."""
        shell = CortexShell()
        assert shell.ai._namespace is shell.namespace

    def test_ai_has_lm(self):
        """AI delegates fill/choose_type to ClaudeCLIBackend."""
        shell = CortexShell()
        assert isinstance(shell.ai._lm, ClaudeCLIBackend)

    def test_ai_no_api_key_needed(self):
        """AI construction succeeds without ANTHROPIC_API_KEY."""
        shell = CortexShell()
        assert shell.ai._call_count == 0

    def test_ai_extract_executable_from_namespace(self):
        """extract_executable is accessible on the namespace ai object."""
        shell = CortexShell()
        blocks = shell.namespace["ai"].extract_executable("<run>\nx = 1\n</run>")
        assert blocks == ["x = 1"]

    def test_nl_stub_removed(self):
        """NL mode no longer contains the Phase 18 stub text."""
        src = inspect.getsource(CortexShell.run)
        assert "Phase 18" not in src
        assert "NL mode coming" not in src


class TestConcurrentSessionRouting:
    """Concurrent AI sessions route namespace mutations correctly."""

    @pytest.mark.asyncio
    async def test_concurrent_sessions_namespace_mutations(self):
        """Two AI sessions mutating shared namespace concurrently both persist."""
        shell = CortexShell()
        ai1 = shell._get_or_create_session("1")
        ai2 = shell._get_or_create_session("2")

        # Mock _send to return code that mutates namespace
        ai1._send = AsyncMock(side_effect=[
            "Setting:\n<run>\nfrom_s1 = True\n</run>",
            "Done from session 1.",
        ])
        ai2._send = AsyncMock(side_effect=[
            "Setting:\n<run>\nfrom_s2 = True\n</run>",
            "Done from session 2.",
        ])

        await asyncio.gather(ai1("prompt 1"), ai2("prompt 2"))

        assert shell.namespace.get("from_s1") is True
        assert shell.namespace.get("from_s2") is True

    @pytest.mark.asyncio
    async def test_concurrent_sessions_router_labels(self):
        """Router.write calls include correct session labels in metadata."""
        shell = CortexShell()
        ai1 = shell._get_or_create_session("1")
        ai2 = shell._get_or_create_session("2")

        ai1._send = AsyncMock(return_value="response 1")
        ai2._send = AsyncMock(return_value="response 2")

        # Replace router.write with a tracker
        writes = []
        original_write = shell.router.write

        def track_write(*args, **kwargs):
            writes.append((args, kwargs))
            original_write(*args, **kwargs)

        shell.router.write = track_write

        await asyncio.gather(ai1("p1"), ai2("p2"))

        ai_writes = [(a, kw) for a, kw in writes if kw.get("metadata", {}).get("type") == "response"]
        labels = {kw["metadata"]["label"] for _, kw in ai_writes}
        assert "1" in labels
        assert "2" in labels


class TestNLSessionRouting:
    """@N prefix in NL mode routes to correct AI session."""

    @pytest.mark.asyncio
    async def test_at_prefix_creates_session(self):
        """@2 prefix creates session 2 and switches to it."""
        shell = CortexShell()

        with patch.object(AI, '_send', new_callable=AsyncMock, return_value="ok"):
            await shell._dispatch("@2 hello")
            # Session switch happens synchronously in _dispatch
            assert shell._active_session == "2"
            assert "2" in shell._ai_sessions

    @pytest.mark.asyncio
    async def test_session_sticky(self):
        """After @2, follow-up without prefix stays on session 2."""
        shell = CortexShell()

        with patch.object(AI, '_send', new_callable=AsyncMock, return_value="ok"):
            await shell._dispatch("@2 hello")
            assert shell._active_session == "2"
            # Follow-up without prefix stays on session 2
            await shell._dispatch("follow up")
            assert shell._active_session == "2"

    @pytest.mark.asyncio
    async def test_at_prefix_switches_back(self):
        """@1 switches back to session 1 after being on session 2."""
        shell = CortexShell()

        with patch.object(AI, '_send', new_callable=AsyncMock, return_value="ok"):
            await shell._dispatch("@2 hello")
            assert shell._active_session == "2"
            await shell._dispatch("@1 back to first")
            assert shell._active_session == "1"
