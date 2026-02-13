"""Bash mode: execute commands via subprocess, cd special-cased."""

from __future__ import annotations

import asyncio
import os

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText


async def dispatch_bash(cmd: str) -> tuple[str, str]:
    """Run a shell command, print output, return (stdout, stderr) strings."""
    cmd = cmd.strip()
    if not cmd:
        return ("", "")

    # cd is special-cased: update REPL's working directory
    if cmd == "cd" or cmd.startswith("cd "):
        target = cmd[3:].strip() if cmd.startswith("cd ") else ""
        target = os.path.expanduser(target or "~")
        try:
            os.chdir(target)
        except (FileNotFoundError, PermissionError) as exc:
            err = f"cd: {exc}"
            print_formatted_text(FormattedText([("fg:red", err)]))
            return ("", err)
        return ("", "")

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd(),
    )
    raw_out, raw_err = await proc.communicate()
    out = raw_out.decode(errors="replace") if raw_out else ""
    err = raw_err.decode(errors="replace") if raw_err else ""
    if out:
        print(out, end="")
    if err:
        print_formatted_text(FormattedText([("fg:red", err)]))
    return (out, err)
