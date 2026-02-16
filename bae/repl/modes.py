"""Mode enum and per-mode config for cortex REPL."""

from __future__ import annotations

from enum import Enum


class Mode(Enum):
    """REPL input modes."""

    NL = "NL"
    PY = "PY"
    BASH = "BASH"


MODE_COLORS: dict[Mode, str] = {
    Mode.NL: "#87d7ff",
    Mode.PY: "#87ff87",
    Mode.BASH: "#d7afff",
}

MODE_NAMES: dict[Mode, str] = {
    Mode.NL: "NL",
    Mode.PY: "PY",
    Mode.BASH: "BASH",
}

DEFAULT_MODE = Mode.NL

# Cycle order for Shift+Tab
MODE_CYCLE = [Mode.NL, Mode.PY, Mode.BASH]
