"""Bash mode: execute commands via subprocess, cd special-cased."""

from __future__ import annotations

import asyncio
import os

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText


async def dispatch_bash(cmd: str) -> None:
    """Run a shell command, printing stdout plain and stderr in red."""
    cmd = cmd.strip()
    if not cmd:
        return

    # cd is special-cased: update REPL's working directory
    if cmd == "cd" or cmd.startswith("cd "):
        target = cmd[3:].strip() if cmd.startswith("cd ") else ""
        target = os.path.expanduser(target or "~")
        try:
            os.chdir(target)
        except (FileNotFoundError, PermissionError) as exc:
            print_formatted_text(FormattedText([("fg:red", f"cd: {exc}")]))
        return

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd(),
    )
    stdout, stderr = await proc.communicate()
    if stdout:
        print(stdout.decode(errors="replace"), end="")
    if stderr:
        print_formatted_text(FormattedText([("fg:red", stderr.decode(errors="replace"))]))
