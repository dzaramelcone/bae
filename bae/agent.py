"""Agent helpers -- executable block extraction for REPL AI.

Extracts executable <run> blocks from LM responses.
"""

from __future__ import annotations

import re


_EXEC_BLOCK_RE = re.compile(
    r"<run>\s*\n?(.*?)\n?\s*</run>",
    re.DOTALL,
)


def extract_executable(text: str) -> list[str]:
    """Extract all executable <run> blocks from text."""
    return _EXEC_BLOCK_RE.findall(text)
