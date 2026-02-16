"""GRAPH mode command dispatcher and handlers."""

from __future__ import annotations

import asyncio
import time
import traceback

from rich.table import Table
from rich.text import Text

from bae.repl.engine import GraphState
from bae.repl.views import _rich_to_ansi


async def dispatch_graph(text: str, shell) -> None:
    """Parse and dispatch GRAPH mode commands."""
    stripped = text.strip()
    if not stripped:
        return
    parts = stripped.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    handlers = {
        "run": _cmd_run,
        "list": _cmd_list,
        "ls": _cmd_list,
        "cancel": _cmd_cancel,
        "inspect": _cmd_inspect,
        "trace": _cmd_trace,
    }
    handler = handlers.get(cmd)
    if handler is None:
        cmds = ", ".join(sorted(set(handlers) - {"ls"}))
        shell.router.write(
            "graph", f"unknown command: {cmd}\navailable: {cmds} (ls = list)",
            mode="GRAPH",
        )
        return
    await handler(arg, shell)


async def _cmd_run(arg: str, shell) -> None:
    """Evaluate <expr> and submit the resulting graph/coroutine to the engine."""
    arg = arg.strip()
    if not arg:
        shell.router.write("graph", "usage: run <expr>", mode="GRAPH")
        return
    try:
        from bae.repl.exec import async_exec

        result, _ = await async_exec(arg, shell.namespace)
    except Exception:
        tb = traceback.format_exc()
        shell.router.write("graph", tb.rstrip("\n"), mode="GRAPH", metadata={"type": "error"})
        return

    if asyncio.iscoroutine(result):
        name = getattr(result, "cr_code", None)
        name = getattr(name, "co_qualname", "graph") if name else "graph"
        run = shell.engine.submit_coro(result, shell.tm, name=name)
    else:
        from bae.graph import Graph

        if isinstance(result, Graph):
            run = shell.engine.submit(result, shell.tm, lm=shell._lm)
        else:
            if asyncio.iscoroutine(result):
                result.close()
            shell.router.write(
                "graph",
                f"expected coroutine or Graph, got {type(result).__name__}",
                mode="GRAPH",
            )
            return

    shell.router.write(
        "graph", f"submitted {run.run_id}", mode="GRAPH",
        metadata={"type": "lifecycle", "run_id": run.run_id},
    )
    _attach_done_callback(run, shell)


def _attach_done_callback(run, shell):
    """Surface task completion/failure/cancellation through the graph channel."""
    for tt in shell.tm.active():
        if tt.name.startswith(f"graph:{run.run_id}:"):
            def _on_done(task, _run=run):
                if task.cancelled():
                    shell.router.write(
                        "graph", f"{_run.run_id} cancelled", mode="GRAPH",
                        metadata={"type": "lifecycle", "run_id": _run.run_id},
                    )
                elif task.exception() is not None:
                    shell.router.write(
                        "graph", f"{_run.run_id} failed: {_run.error}", mode="GRAPH",
                        metadata={"type": "error", "run_id": _run.run_id},
                    )
                else:
                    shell.router.write(
                        "graph", f"{_run.run_id} done", mode="GRAPH",
                        metadata={"type": "lifecycle", "run_id": _run.run_id},
                    )
            tt.task.add_done_callback(_on_done)
            break


async def _cmd_list(arg: str, shell) -> None:
    """Show all graph runs with state, elapsed time, and current node."""
    runs = shell.engine.active() + list(shell.engine._completed)
    if not runs:
        shell.router.write("graph", "(no graph runs)", mode="GRAPH")
        return
    table = Table(show_header=True, header_style="bold")
    table.add_column("ID")
    table.add_column("STATE")
    table.add_column("ELAPSED")
    table.add_column("NODE")
    now = time.perf_counter_ns()
    for run in runs:
        if run.ended_ns > 0:
            elapsed = (run.ended_ns - run.started_ns) / 1e9
        else:
            elapsed = (now - run.started_ns) / 1e9
        table.add_row(
            run.run_id,
            run.state.value,
            f"{elapsed:.1f}s",
            run.current_node or "-",
        )
    shell.router.write("graph", _rich_to_ansi(table).rstrip("\n"), mode="GRAPH")


async def _cmd_cancel(arg: str, shell) -> None:
    """Cancel a running graph by run_id."""
    arg = arg.strip()
    if not arg:
        shell.router.write("graph", "usage: cancel <id>", mode="GRAPH")
        return
    run = shell.engine.get(arg)
    if run is None:
        shell.router.write("graph", f"no run {arg}", mode="GRAPH")
        return
    if run.state != GraphState.RUNNING:
        shell.router.write(
            "graph", f"{arg} not running ({run.state.value})", mode="GRAPH",
        )
        return
    for tt in shell.tm.active():
        if tt.name.startswith(f"graph:{run.run_id}:"):
            shell.tm.revoke(tt.task_id)
            break
    shell.router.write("graph", f"cancelled {run.run_id}", mode="GRAPH")


async def _cmd_inspect(arg: str, shell) -> None:
    """Display full execution trace with node timings and field values."""
    arg = arg.strip()
    if not arg:
        shell.router.write("graph", "usage: inspect <id>", mode="GRAPH")
        return
    run = shell.engine.get(arg)
    if run is None:
        shell.router.write("graph", f"no run {arg}", mode="GRAPH")
        return

    now = time.perf_counter_ns()
    if run.ended_ns > 0:
        elapsed = (run.ended_ns - run.started_ns) / 1e9
    else:
        elapsed = (now - run.started_ns) / 1e9

    parts = []
    parts.append(f"Run {run.run_id} ({run.state.value}, {elapsed:.1f}s)")
    if run.graph:
        parts.append(f"Graph: {run.graph.start.__name__}")

    if run.node_timings:
        parts.append("")
        parts.append("Timings:")
        for nt in run.node_timings:
            parts.append(f"  {nt.node_type}  {nt.duration_ms:.0f}ms")

    if run.result and run.result.trace:
        parts.append("")
        parts.append("Trace:")
        trace = run.result.trace
        for i, node in enumerate(trace, 1):
            if i == len(trace):
                # Terminal node: show all fields
                fields = node.model_dump()
                parts.append(f"  {i}. {type(node).__name__}  {fields}")
            else:
                parts.append(f"  {i}. {type(node).__name__}")

    text = Text("\n".join(parts))
    shell.router.write("graph", _rich_to_ansi(text).rstrip("\n"), mode="GRAPH")


async def _cmd_trace(arg: str, shell) -> None:
    """Show compact node transition history."""
    arg = arg.strip()
    if not arg:
        shell.router.write("graph", "usage: trace <id>", mode="GRAPH")
        return
    run = shell.engine.get(arg)
    if run is None:
        shell.router.write("graph", f"no run {arg}", mode="GRAPH")
        return
    if not (run.result and run.result.trace):
        shell.router.write("graph", f"{arg}: no trace available", mode="GRAPH")
        return

    # Build timing lookup
    timing_map: dict[str, float] = {}
    for nt in run.node_timings:
        timing_map[nt.node_type] = nt.duration_ms

    lines = []
    for i, node in enumerate(run.result.trace, 1):
        name = type(node).__name__
        ms = timing_map.get(name)
        if ms is not None:
            lines.append(f"  {i}. {name}  {ms:.0f}ms")
        else:
            lines.append(f"  {i}. {name}")

    shell.router.write("graph", "\n".join(lines), mode="GRAPH")
