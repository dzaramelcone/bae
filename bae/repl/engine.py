"""Graph engine: registry, lifecycle tracking, and per-node timing."""

from __future__ import annotations

import asyncio
import enum
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bae.lm import LM
from bae.resolver import GATE_HOOK_KEY, LM_KEY, _engine_dep_cache

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
        self._gate_counter: int = 0

    def submit(
        self,
        graph: Graph,
        tm: TaskManager,
        *,
        lm: LM | None = None,
        notify=None,
        **kwargs,
    ) -> GraphRun:
        run_id = f"g{self._next_id}"
        self._next_id += 1
        run = GraphRun(run_id=run_id, graph=graph)
        self._runs[run_id] = run
        coro = self._execute(run, lm=lm, notify=notify, **kwargs)
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
                    notify(f"[{g.gate_id}] {g.node_type}.{g.schema_display}")
            results = await asyncio.gather(*[g.future for g in gates])
            run.state = GraphState.RUNNING
            return {g.field_name: val for g, val in zip(gates, results)}
        return hook

    async def _execute(
        self, run: GraphRun, *, lm: LM | None = None, notify=None, **kwargs,
    ):
        try:
            if lm is None:
                from bae.lm import ClaudeCLIBackend
                lm = ClaudeCLIBackend()
            timing_lm = TimingLM(lm, run)

            dep_cache = {
                LM_KEY: timing_lm,
                GATE_HOOK_KEY: self._make_gate_hook(run, notify),
            }
            result = await run.graph.arun(lm=timing_lm, dep_cache=dep_cache, **kwargs)
            run.result = result
            run.state = GraphState.DONE
            return result
        except asyncio.CancelledError:
            run.state = GraphState.CANCELLED
            self.cancel_gates(run.run_id)
            raise
        except Exception as e:
            run.state = GraphState.FAILED
            run.error = f"{type(e).__name__}: {e}"
            if hasattr(e, "trace"):
                from bae.result import GraphResult
                run.result = GraphResult(node=None, trace=e.trace)
            raise
        finally:
            run.ended_ns = time.perf_counter_ns()
            self._archive(run)

    def submit_coro(
        self, coro, tm: TaskManager, *, name: str = "graph", notify=None,
    ) -> GraphRun:
        """Submit a pre-built coroutine as a managed graph run.

        Used when `run <expr>` evaluates to an already-constructed coroutine
        (e.g., `ootd(user_info=..., user_message=...)`). The gate hook is
        injected via contextvar so arun picks it up automatically.
        """
        run_id = f"g{self._next_id}"
        self._next_id += 1
        run = GraphRun(run_id=run_id, graph=None)
        self._runs[run_id] = run
        wrapped = self._wrap_coro(run, coro, notify=notify)
        tm.submit(wrapped, name=f"graph:{run_id}:{name}", mode="graph")
        return run

    async def _wrap_coro(self, run: GraphRun, coro, *, notify=None):
        """Wrap a coroutine with lifecycle tracking and gate hook injection."""
        token = _engine_dep_cache.set(
            {GATE_HOOK_KEY: self._make_gate_hook(run, notify)}
        )
        try:
            result = await coro
            run.state = GraphState.DONE
            if hasattr(result, "trace"):
                run.result = result
            return result
        except asyncio.CancelledError:
            run.state = GraphState.CANCELLED
            self.cancel_gates(run.run_id)
            raise
        except Exception as e:
            run.state = GraphState.FAILED
            run.error = f"{type(e).__name__}: {e}"
            if hasattr(e, "trace"):
                from bae.result import GraphResult
                run.result = GraphResult(node=None, trace=e.trace)
            raise
        finally:
            _engine_dep_cache.reset(token)
            run.ended_ns = time.perf_counter_ns()
            self._archive(run)

    def _archive(self, run: GraphRun) -> None:
        self._runs.pop(run.run_id, None)
        self._completed.append(run)

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
        gate_id = f"{run_id}.{self._gate_counter}"
        self._gate_counter += 1
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
