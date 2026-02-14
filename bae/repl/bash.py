"""Bash mode: execute commands via subprocess, cd special-cased."""

from __future__ import annotations

import asyncio
import os


async def dispatch_bash(cmd: str, *, tm=None) -> tuple[str, str]:
    """Run a shell command, return (stdout, stderr) strings.

    The caller is responsible for display via channels.
    """
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
            return ("", f"cd: {exc}")
        return ("", "")

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=os.getcwd(),
        start_new_session=True,
    )
    if tm is not None:
        tm.register_process(proc)
    try:
        raw_out, raw_err = await proc.communicate()
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    out = raw_out.decode(errors="replace") if raw_out else ""
    err = raw_err.decode(errors="replace") if raw_err else ""
    return (out, err)
