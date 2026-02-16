"""Configurable user input callback for work graphs."""

from __future__ import annotations

from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel

from bae import Dep


class PromptChoice(BaseModel):
    label: str
    description: str = ""


class PromptResult(BaseModel):
    text: str
    selected: list[str] = []
    approved: bool = True


@runtime_checkable
class Prompt(Protocol):
    """Pluggable callback for getting user input during graph execution.

    Implementations:
    - TerminalPrompt: input() for CLI usage
    - TestPrompt: pre-loaded answers for integration tests
    """

    async def ask(
        self,
        question: str,
        *,
        choices: list[PromptChoice] | None = None,
        multi_select: bool = False,
    ) -> PromptResult: ...

    async def confirm(self, message: str) -> bool: ...


class TerminalPrompt:
    """Default: blocking input() for terminal usage."""

    async def ask(self, question, *, choices=None, multi_select=False):
        import asyncio

        loop = asyncio.get_event_loop()
        if choices:
            for i, c in enumerate(choices, 1):
                desc = f" -- {c.description}" if c.description else ""
                question += f"\n  {i}. {c.label}{desc}"
        text = await loop.run_in_executor(None, input, f"\n{question}\n> ")
        return PromptResult(text=text)

    async def confirm(self, message):
        import asyncio

        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, input, f"\n{message} (y/n) > ")
        return text.strip().lower() in ("y", "yes")


_prompt: Prompt = TerminalPrompt()


def get_prompt() -> Prompt:
    """Returns the configured Prompt implementation."""
    return _prompt


PromptDep = Annotated[Prompt, Dep(get_prompt)]


# -- Gate Deps: user confirmation as injectable dependencies ------------------

_GATES: dict[str, tuple[str, str]] = {
    "confirm_continue":   ("Continue?",                "Generic continue gate."),
    "confirm_refresh":    ("Maps exist. Refresh?",     "Refresh existing data gate."),
    "confirm_secrets":    ("Proceed despite secrets?",  "Proceed despite secret findings gate."),
    "confirm_failures":   ("Continue despite failures?", "Continue despite failures gate."),
    "confirm_blockers":   ("Continue despite blockers?", "Continue despite blockers gate."),
    "confirm_approve":    ("Approve?",                  "Generic approval gate."),
    "confirm_brownfield": ("Map codebase first?",       "Map existing codebase gate."),
}


def _gate(name: str, msg: str, doc: str):
    """Factory for gate confirmation functions."""
    async def gate(prompt: PromptDep) -> bool:
        return await prompt.confirm(msg)
    gate.__name__ = name
    gate.__qualname__ = name
    gate.__module__ = __name__
    gate.__doc__ = doc
    return gate


# Generate gate functions and Annotated aliases from the dict
for _name, (_msg, _doc) in _GATES.items():
    globals()[_name] = _gate(_name, _msg, _doc)

_GATE_ALIASES = {
    "ContinueGate":   "confirm_continue",
    "RefreshGate":    "confirm_refresh",
    "SecretsGate":    "confirm_secrets",
    "FailuresGate":   "confirm_failures",
    "BlockersGate":   "confirm_blockers",
    "ApproveGate":    "confirm_approve",
    "BrownfieldGate": "confirm_brownfield",
}

for _alias, _fn_name in _GATE_ALIASES.items():
    globals()[_alias] = Annotated[bool, Dep(globals()[_fn_name])]
