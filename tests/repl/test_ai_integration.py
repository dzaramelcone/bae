"""Integration tests for AI wiring in CortexShell."""

from __future__ import annotations

import inspect

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

    def test_ai_extract_code_from_namespace(self):
        """extract_code is accessible on the namespace ai object."""
        shell = CortexShell()
        blocks = shell.namespace["ai"].extract_code("```python\nx = 1\n```")
        assert blocks == ["x = 1"]

    def test_nl_stub_removed(self):
        """NL mode no longer contains the Phase 18 stub text."""
        src = inspect.getsource(CortexShell.run)
        assert "Phase 18" not in src
        assert "NL mode coming" not in src
