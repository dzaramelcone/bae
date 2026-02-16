"""Home resourcespace filesystem tools.

Read, write, edit, glob, and grep operations for the home (root) context.
These are the filesystem tool implementations used when no resourcespace
is navigated into.
"""

from __future__ import annotations

import re
from pathlib import Path

_MAX_TOOL_OUTPUT = 4000

_LINE_RANGE_RE = re.compile(r"^(.+?):(\d+)[-:](\d+)$")


def _exec_read(arg: str) -> str:
    arg = arg.strip()
    m = _LINE_RANGE_RE.match(arg)
    if m:
        return _exec_edit_read(arg)
    content = Path(arg).read_text()
    if len(content) > _MAX_TOOL_OUTPUT:
        return content[:_MAX_TOOL_OUTPUT] + "\n... (truncated)"
    return content


def _exec_write(filepath: str, content: str) -> str:
    fp = filepath.strip()
    Path(fp).parent.mkdir(parents=True, exist_ok=True)
    Path(fp).write_text(content)
    return f"Wrote {len(content)} chars to {fp}"


def _exec_edit_read(arg: str) -> str:
    arg = arg.strip()
    m = _LINE_RANGE_RE.match(arg)
    if m:
        fp = m.group(1).strip()
        s, e = int(m.group(2)), int(m.group(3))
        lines = Path(fp).read_text().splitlines(True)
        return "".join(
            f"{i:4d} | {ln}" for i, ln in enumerate(lines[s - 1:e], start=s)
        )
    return _exec_read(arg)


def _exec_edit_replace(filepath: str, start: int, end: int, content: str) -> str:
    fp = filepath.strip()
    lines = Path(fp).read_text().splitlines(True)
    lines[start - 1:end] = content.splitlines(True)
    Path(fp).write_text("".join(lines))
    return f"Replaced lines {start}-{end} in {fp}"


def _exec_glob(pattern: str) -> str:
    import glob as g
    p = pattern.strip()
    hits = sorted(g.glob(p, recursive=True))
    limit = _MAX_TOOL_OUTPUT // 40
    result = "\n".join(hits[:limit])
    if len(hits) > limit:
        result += f"\n... ({len(hits)} total)"
    return result or "(no matches)"


def _exec_grep(arg: str) -> str:
    arg = arg.strip()
    parts = arg.rsplit(" ", 1)
    if len(parts) == 2 and ("/" in parts[1] or parts[1].endswith(".py")):
        pattern, path = parts[0].strip('"').strip("'"), parts[1]
    else:
        pattern, path = arg.strip('"').strip("'"), "."
    skip = {".venv", ".git", "__pycache__", "node_modules"}
    matches: list[str] = []
    limit = _MAX_TOOL_OUTPUT // 80
    p = Path(path)
    files = [p] if p.is_file() else sorted(p.rglob("*.py"))
    for f in files:
        if skip & set(f.parts):
            continue
        try:
            for i, ln in enumerate(f.read_text().splitlines(), 1):
                if re.search(pattern, ln):
                    matches.append(f"{f}:{i}:{ln}")
        except (OSError, UnicodeDecodeError):
            pass
    result = "\n".join(matches[:limit])
    if len(matches) > limit:
        result += f"\n... ({len(matches)} total matches)"
    return result or "(no matches)"
