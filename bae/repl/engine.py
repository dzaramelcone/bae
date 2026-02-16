"""Graph engine: registry, lifecycle tracking, and per-node timing."""

from __future__ import annotations

import asyncio
import contextvars
import enum
import logging
import resource
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bae.lm import LM
from bae.resolver import DEP_TIMING_KEY, GATE_HOOK_KEY, LM_KEY, _engine_dep_cache

# Contextvar for auto-registration: (engine, tm, lm, notify)
_graph_ctx: contextvars.ContextVar[tuple | None] = contextvars.ContextVar(
    "_graph_ctx", default=None
)

_graph_logger = logging.getLogger("bae.graph")


class _NotifyHandler(logging.Handler):
    """Forward graph logger messages to the engine's notify callback."""

    def __init__(self, run_id: str, notify):
        super().__init__(logging.INFO)
        self._run_id = run_id
        self._notify = notify

    def emit(self, record):
        self._notify(
            f"{self._run_id} {record.getMessage()}",
            {"type": "lifecycle", "event": "transition", "run_id": self._run_id},
        )

if TYPE_CHECKING:
    from bae.graph import Graph
    from bae.repl.tasks import TaskManager
    from bae.result import GraphResult


class GraphState(enum.Enum):
    RUNNING = "running"
    WAITING = "waiting"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutputPolicy(enum.Enum):
    VERBOSE = "verbose"
    NORMAL = "normal"
    QUIET = "quiet"
    SILENT = "silent"

    def should_emit(self, event: str) -> bool:
        if self == OutputPolicy.SILENT:
            return False
        if self == OutputPolicy.QUIET:
            return event in ("fail", "cancel", "gate", "error")
        if self == OutputPolicy.NORMAL:
            return event in ("start", "complete", "fail", "cancel", "gate", "error")
        return True  # VERBOSE


@dataclass
class NodeTiming:
    node_type: str
    start_ns: int
    end_ns: int = 0

    @property
    def duration_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1_000_000


@dataclass
class GraphRun:
    run_id: str
    graph: Graph | None
    state: GraphState = GraphState.RUNNING
    node_timings: list[NodeTiming] = field(default_factory=list)
    current_node: str = ""
    started_ns: int = field(default_factory=time.perf_counter_ns)
    ended_ns: int = 0
    error: str = ""
    result: GraphResult | None = None
    dep_timings: list[tuple[str, float]] = field(default_factory=list)
    rss_delta_bytes: int = 0
    policy: OutputPolicy = OutputPolicy.NORMAL
    _done: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class InputGate:
    """Future wrapper with schema metadata for human input gates.

    Created by the engine when a gate-annotated field is encountered
    during graph execution. The Future suspends execution until the
    user provides a value.
    """

    gate_id: str
    run_id: str
    field_name: str
    field_type: type
    description: str
    node_type: str
    future: asyncio.Future = field(
        default_factory=lambda: asyncio.get_event_loop().create_future()
    )

    @property
    def schema_display(self) -> str:
        """Human-readable prompt: field_name: type ("description")."""
        type_name = getattr(self.field_type, "__name__", str(self.field_type))
        if self.description:
            return f'{self.field_name}: {type_name} ("{self.description}")'
        return f"{self.field_name}: {type_name}"


def _get_rss_bytes() -> int:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if sys.platform == "darwin" else rss * 1024


class TimingLM:
    """LM wrapper that records fill durations for engine instrumentation."""

    def __init__(self, inner: LM, run: GraphRun):
        self._inner = inner
        self._run = run

    async def fill(self, target, resolved, instruction, source=None):
        start = time.perf_counter_ns()
        result = await self._inner.fill(target, resolved, instruction, source)
        end = time.perf_counter_ns()
        self._run.current_node = target.__name__
        self._run.node_timings.append(
            NodeTiming(node_type=target.__name__, start_ns=start, end_ns=end)
        )
        return result

    async def choose_type(self, types, context):
        return await self._inner.choose_type(types, context)

    async def make(self, node, target):
        start = time.perf_counter_ns()
        result = await self._inner.make(node, target)
        end = time.perf_counter_ns()
        self._run.current_node = target.__name__
        self._run.node_timings.append(
            NodeTiming(node_type=target.__name__, start_ns=start, end_ns=end)
        )
        return result

    async def decide(self, node):
        return await self._inner.decide(node)


class GraphRegistry:
    def __init__(self):
        self._runs: dict[str, GraphRun] = {}
        self._next_id: int = 1
        self._completed: deque[GraphRun] = deque(maxlen=20)
        self._pending_gates: dict[str, InputGate] = {}
        self._gate_counters: dict[str, int] = {}  # per-graph gate counter

    def submit(
        self,
        graph: Graph,
        tm: TaskManager,
        *,
        lm: LM | None = None,
        notify=None,
        policy: OutputPolicy = OutputPolicy.NORMAL,
        **kwargs,
    ) -> GraphRun:
        run_id = f"g{self._next_id}"
        self._next_id += 1
        run = GraphRun(run_id=run_id, graph=graph, policy=policy)
        self._runs[run_id] = run
        coro = self._execute(run, lm=lm, notify=notify, policy=policy, **kwargs)
        tm.submit(coro, name=f"graph:{run_id}:{graph.start.__name__}", mode="graph")
        return run

    def _make_gate_hook(self, run: GraphRun, notify=None):
        """Build a gate hook closure for a specific graph run."""
        async def hook(node_cls, gate_fields):
            gates = []
            for field_name, field_type, description in gate_fields:
                gate = self.create_gate(
                    run.run_id, field_name, field_type, description,
                    node_cls.__name__,
                )
                gates.append(gate)
            run.state = GraphState.WAITING
            if notify is not None:
                for g in gates:
                    notify(
                        f"[{g.gate_id}] {g.node_type}.{g.schema_display}",
                        {"type": "gate", "run_id": run.run_id, "gate_id": g.gate_id},
                    )
            results = await asyncio.gather(*[g.future for g in gates])
            run.state = GraphState.RUNNING
            return {g.field_name: val for g, val in zip(gates, results)}
        return hook

    async def _execute(
        self,
        run: GraphRun,
        *,
        lm: LM | None = None,
        notify=None,
        policy: OutputPolicy = OutputPolicy.NORMAL,
        **kwargs,
    ):
        run.policy = policy

        def _emit(event, content, meta=None):
            if policy.should_emit(event) and notify:
                notify(content, meta)

        def _dep_timing_hook(name, duration_ms):
            run.dep_timings.append((name, duration_ms))

        log_handler = None
        if policy == OutputPolicy.VERBOSE and notify:
            log_handler = _NotifyHandler(run.run_id, notify)
            _graph_logger.addHandler(log_handler)

        try:
            if lm is None:
                from bae.lm import ClaudeCLIBackend
                lm = ClaudeCLIBackend()
            timing_lm = TimingLM(lm, run)

            dep_cache = {
                LM_KEY: timing_lm,
                GATE_HOOK_KEY: self._make_gate_hook(run, notify),
                DEP_TIMING_KEY: _dep_timing_hook,
            }

            _emit("start", f"{run.run_id} started", {
                "type": "lifecycle", "event": "start", "run_id": run.run_id,
            })

            rss_before = _get_rss_bytes()
            result = await run.graph.arun(lm=timing_lm, dep_cache=dep_cache, **kwargs)
            rss_after = _get_rss_bytes()
            run.rss_delta_bytes = rss_after - rss_before

            run.result = result
            run.state = GraphState.DONE

            elapsed_s = (time.perf_counter_ns() - run.started_ns) / 1e9
            _emit("complete", f"{run.run_id} done ({elapsed_s:.1f}s)", {
                "type": "lifecycle", "event": "complete", "run_id": run.run_id,
            })

            return result
        except asyncio.CancelledError:
            run.state = GraphState.CANCELLED
            self.cancel_gates(run.run_id)
            _emit("cancel", f"{run.run_id} cancelled", {
                "type": "lifecycle", "event": "cancel", "run_id": run.run_id,
            })
            raise
        except Exception as e:
            run.state = GraphState.FAILED
            run.error = f"{type(e).__name__}: {e}"
            if hasattr(e, "trace"):
                from bae.result import GraphResult
                run.result = GraphResult(node=None, trace=e.trace)
            _emit("fail", f"{run.run_id} failed: {run.error}", {
                "type": "lifecycle", "event": "fail", "run_id": run.run_id,
            })
            raise
        finally:
            if log_handler:
                _graph_logger.removeHandler(log_handler)
            run.ended_ns = time.perf_counter_ns()
            self._archive(run)

    def submit_coro(
        self,
        coro,
        tm: TaskManager,
        *,
        name: str = "graph",
        notify=None,
        policy: OutputPolicy = OutputPolicy.NORMAL,
    ) -> GraphRun:
        """Submit a pre-built coroutine as a managed graph run.

        Used when `run <expr>` evaluates to an already-constructed coroutine
        (e.g., `ootd(user_info=..., user_message=...)`). The gate hook is
        injected via contextvar so arun picks it up automatically.
        """
        run_id = f"g{self._next_id}"
        self._next_id += 1
        run = GraphRun(run_id=run_id, graph=None, policy=policy)
        self._runs[run_id] = run
        wrapped = self._wrap_coro(run, coro, notify=notify, policy=policy)
        tm.submit(wrapped, name=f"graph:{run_id}:{name}", mode="graph")
        return run

    async def _wrap_coro(
        self,
        run: GraphRun,
        coro,
        *,
        notify=None,
        policy: OutputPolicy = OutputPolicy.NORMAL,
    ):
        """Wrap a coroutine with lifecycle tracking and gate hook injection."""
        run.policy = policy

        def _emit(event, content, meta=None):
            if policy.should_emit(event) and notify:
                notify(content, meta)

        def _dep_timing_hook(name, duration_ms):
            run.dep_timings.append((name, duration_ms))

        log_handler = None
        if policy == OutputPolicy.VERBOSE and notify:
            log_handler = _NotifyHandler(run.run_id, notify)
            _graph_logger.addHandler(log_handler)

        token = _engine_dep_cache.set({
            GATE_HOOK_KEY: self._make_gate_hook(run, notify),
            DEP_TIMING_KEY: _dep_timing_hook,
        })
        try:
            _emit("start", f"{run.run_id} started", {
                "type": "lifecycle", "event": "start", "run_id": run.run_id,
            })

            rss_before = _get_rss_bytes()
            result = await coro
            rss_after = _get_rss_bytes()
            run.rss_delta_bytes = rss_after - rss_before

            run.state = GraphState.DONE
            if hasattr(result, "trace"):
                run.result = result

            elapsed_s = (time.perf_counter_ns() - run.started_ns) / 1e9
            _emit("complete", f"{run.run_id} done ({elapsed_s:.1f}s)", {
                "type": "lifecycle", "event": "complete", "run_id": run.run_id,
            })

            return result
        except asyncio.CancelledError:
            run.state = GraphState.CANCELLED
            self.cancel_gates(run.run_id)
            _emit("cancel", f"{run.run_id} cancelled", {
                "type": "lifecycle", "event": "cancel", "run_id": run.run_id,
            })
            raise
        except Exception as e:
            run.state = GraphState.FAILED
            run.error = f"{type(e).__name__}: {e}"
            if hasattr(e, "trace"):
                from bae.result import GraphResult
                run.result = GraphResult(node=None, trace=e.trace)
            _emit("fail", f"{run.run_id} failed: {run.error}", {
                "type": "lifecycle", "event": "fail", "run_id": run.run_id,
            })
            raise
        finally:
            if log_handler:
                _graph_logger.removeHandler(log_handler)
            _engine_dep_cache.reset(token)
            run.ended_ns = time.perf_counter_ns()
            self._archive(run)

    def _archive(self, run: GraphRun) -> None:
        self._runs.pop(run.run_id, None)
        self._completed.append(run)
        run._done.set()

    # ── Gate lifecycle ───────────────────────────────────────────────────

    def create_gate(
        self,
        run_id: str,
        field_name: str,
        field_type: type,
        description: str,
        node_type: str,
    ) -> InputGate:
        """Create and register an InputGate for a pending human input."""
        counter = self._gate_counters.get(run_id, 0)
        gate_id = f"{run_id}.{counter}"
        self._gate_counters[run_id] = counter + 1
        gate = InputGate(
            gate_id=gate_id,
            run_id=run_id,
            field_name=field_name,
            field_type=field_type,
            description=description,
            node_type=node_type,
        )
        self._pending_gates[gate_id] = gate
        return gate

    def resolve_gate(self, gate_id: str, value: object) -> bool:
        """Resolve a pending gate with a value. Returns False if not found."""
        gate = self._pending_gates.pop(gate_id, None)
        if gate is None or gate.future.done():
            return False
        gate.future.set_result(value)
        return True

    def get_pending_gate(self, gate_id: str) -> InputGate | None:
        """Look up a pending gate by ID."""
        return self._pending_gates.get(gate_id)

    def pending_gate_count(self) -> int:
        """Number of gates awaiting user input."""
        return len(self._pending_gates)

    def pending_gates_for_run(self, run_id: str) -> list[InputGate]:
        """All pending gates belonging to a specific graph run."""
        return [g for g in self._pending_gates.values() if g.run_id == run_id]

    def cancel_gates(self, run_id: str) -> None:
        """Cancel all pending gates for a run and remove from registry."""
        to_remove = [
            gid for gid, g in self._pending_gates.items() if g.run_id == run_id
        ]
        for gid in to_remove:
            gate = self._pending_gates.pop(gid)
            if not gate.future.done():
                gate.future.cancel()

    def active(self) -> list[GraphRun]:
        return [
            r for r in self._runs.values()
            if r.state in (GraphState.RUNNING, GraphState.WAITING)
        ]

    def get(self, run_id: str) -> GraphRun | None:
        run = self._runs.get(run_id)
        if run:
            return run
        for r in self._completed:
            if r.run_id == run_id:
                return r
        return None
