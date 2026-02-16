"""Agent helpers -- executable block extraction for REPL AI.

Extracts executable <run> blocks from LM responses.
"""

from __future__ import annotations

import re


_EXEC_BLOCK_RE = re.compile(
    r"<run>\s*\n?(.*?)\n?\s*</run>",
    re.DOTALL,
)


def extract_executable(text: str) -> tuple[str | None, int]:
    """Extract first executable <run> block and count of extras.

    Returns (code, extra_count) where code is the first executable
    block or None, and extra_count is additional blocks ignored.
    """
    matches = _EXEC_BLOCK_RE.findall(text)
    if not matches:
        return None, 0
    return matches[0], len(matches) - 1
