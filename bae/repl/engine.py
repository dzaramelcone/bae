"""Graph engine: registry, lifecycle tracking, and per-node timing."""

from __future__ import annotations

import asyncio
import enum
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bae.lm import LM
from bae.resolver import LM_KEY

if TYPE_CHECKING:
    from bae.graph import Graph
    from bae.repl.tasks import TaskManager
    from bae.result import GraphResult


class GraphState(enum.Enum):
    RUNNING = "running"
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

    def submit(
        self, graph: Graph, tm: TaskManager, *, lm: LM | None = None, **kwargs
    ) -> GraphRun:
        run_id = f"g{self._next_id}"
        self._next_id += 1
        run = GraphRun(run_id=run_id, graph=graph)
        self._runs[run_id] = run
        coro = self._execute(run, lm=lm, **kwargs)
        tm.submit(coro, name=f"graph:{run_id}:{graph.start.__name__}", mode="graph")
        return run

    async def _execute(self, run: GraphRun, *, lm: LM | None = None, **kwargs):
        try:
            if lm is None:
                from bae.lm import ClaudeCLIBackend
                lm = ClaudeCLIBackend()
            timing_lm = TimingLM(lm, run)
            dep_cache = {LM_KEY: timing_lm}
            result = await run.graph.arun(lm=timing_lm, dep_cache=dep_cache, **kwargs)
            run.result = result
            run.state = GraphState.DONE
            return result
        except asyncio.CancelledError:
            run.state = GraphState.CANCELLED
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
        self, coro, tm: TaskManager, *, name: str = "graph",
    ) -> GraphRun:
        """Submit a pre-built coroutine as a managed graph run.

        Used when `run <expr>` evaluates to an already-constructed coroutine
        (e.g., `ootd(user_info=..., user_message=...)`). The coroutine is
        wrapped with lifecycle tracking but TimingLM cannot be injected
        since the LM is already bound inside the coroutine.
        """
        run_id = f"g{self._next_id}"
        self._next_id += 1
        run = GraphRun(run_id=run_id, graph=None)
        self._runs[run_id] = run
        wrapped = self._wrap_coro(run, coro)
        tm.submit(wrapped, name=f"graph:{run_id}:{name}", mode="graph")
        return run

    async def _wrap_coro(self, run: GraphRun, coro):
        """Wrap a coroutine with lifecycle tracking."""
        try:
            result = await coro
            run.state = GraphState.DONE
            if hasattr(result, "trace"):
                run.result = result
            return result
        except asyncio.CancelledError:
            run.state = GraphState.CANCELLED
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

    def _archive(self, run: GraphRun) -> None:
        self._runs.pop(run.run_id, None)
        self._completed.append(run)

    def active(self) -> list[GraphRun]:
        return [r for r in self._runs.values() if r.state == GraphState.RUNNING]

    def get(self, run_id: str) -> GraphRun | None:
        run = self._runs.get(run_id)
        if run:
            return run
        for r in self._completed:
            if r.run_id == run_id:
                return r
        return None
