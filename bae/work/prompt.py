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


async def confirm_continue(prompt: PromptDep) -> bool:
    """Generic continue gate."""
    return await prompt.confirm("Continue?")


async def confirm_refresh(prompt: PromptDep) -> bool:
    """Refresh existing data gate."""
    return await prompt.confirm("Maps exist. Refresh?")


async def confirm_secrets(prompt: PromptDep) -> bool:
    """Proceed despite secret findings gate."""
    return await prompt.confirm("Proceed despite secrets?")


async def confirm_failures(prompt: PromptDep) -> bool:
    """Continue despite failures gate."""
    return await prompt.confirm("Continue despite failures?")


async def confirm_blockers(prompt: PromptDep) -> bool:
    """Continue despite blockers gate."""
    return await prompt.confirm("Continue despite blockers?")


async def confirm_approve(prompt: PromptDep) -> bool:
    """Generic approval gate."""
    return await prompt.confirm("Approve?")


async def confirm_brownfield(prompt: PromptDep) -> bool:
    """Map existing codebase gate."""
    return await prompt.confirm("Map codebase first?")


ContinueGate = Annotated[bool, Dep(confirm_continue)]
RefreshGate = Annotated[bool, Dep(confirm_refresh)]
SecretsGate = Annotated[bool, Dep(confirm_secrets)]
FailuresGate = Annotated[bool, Dep(confirm_failures)]
BlockersGate = Annotated[bool, Dep(confirm_blockers)]
ApproveGate = Annotated[bool, Dep(confirm_approve)]
BrownfieldGate = Annotated[bool, Dep(confirm_brownfield)]
