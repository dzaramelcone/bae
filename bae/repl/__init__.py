"""Cortex: async REPL with mode switching."""

from __future__ import annotations

import asyncio

from bae.repl.modes import Mode
from bae.repl.shell import CortexShell


def launch() -> None:
    """Start the cortex REPL."""
    asyncio.run(CortexShell().run())


__all__ = ["CortexShell", "Mode", "launch"]
