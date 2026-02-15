"""Map codebase workflow -- parallel agents with secret scan gate.

Graph:
    InitMapCodebase -+-> UseExisting (skip, None)
                     +-> SpawnMappers -> VerifyOutput -> ScanSecrets -+-> ReviewSecrets -> CommitMaps
                                                                     +-> CommitMaps (clean)
                                                                              |
                                                                         MappingDone
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from bae import Dep, Effect, Graph, Node, Recall
from bae.lm import ClaudeCLIBackend

from bae.work.deps import check_existing, scan_secrets, vcs_commit_maps
from bae.work.models import ExistingMaps, MapperResult, SecretScanResult
from bae.work.prompt import RefreshGate, SecretsGate


# -- Mapper sub-graph (runs per focus area) ----------------------------------


class MapFocus(Node):
    """Map a single focus area of the codebase."""

    focus: str

    async def __call__(self) -> MapFocusDone: ...


class MapFocusDone(Node):
    """Terminal: mapping complete for one focus area."""

    focus: str
    documents: list[str]
    line_counts: dict[str, int]

    async def __call__(self) -> None: ...


# -- Dep function for parallel mapper agents ----------------------------------


async def run_mapper_agents() -> list[MapperResult]:
    """4 parallel mapper agents, each mapping a focus area."""
    lm = ClaudeCLIBackend()
    focuses = ["tech", "arch", "quality", "concerns"]

    async def map_one(focus: str) -> MapperResult:
        g = Graph(start=MapFocus)
        result = await g.arun(MapFocus(focus=focus), lm=lm)
        done = result.trace[-1]
        return MapperResult(
            focus=done.focus,
            documents=done.documents,
            line_counts=done.line_counts,
        )

    return list(await asyncio.gather(*[map_one(f) for f in focuses]))


MappersDep = Annotated[list[MapperResult], Dep(run_mapper_agents)]


# -- Main graph nodes ---------------------------------------------------------


class InitMapCodebase(Node):
    """Entry point: decide whether to refresh or use existing maps."""

    project_root: str
    existing: Annotated[ExistingMaps, Dep(check_existing)] = None
    approved: RefreshGate = None

    async def __call__(self) -> SpawnMappers | None: ...


class SpawnMappers(Node):
    """Run 4 parallel mapper agents."""

    results: MappersDep

    async def __call__(self) -> VerifyOutput: ...


class VerifyOutput(Node):
    """Verify all mapper outputs are present."""

    results: Annotated[list[MapperResult], Recall()]
    all_present: bool
    gaps: list[str]

    async def __call__(self) -> ScanSecrets: ...


class ScanSecrets(Node):
    """Scan outputs for secrets before committing."""

    scan: Annotated[SecretScanResult, Dep(scan_secrets)]

    async def __call__(self) -> ReviewSecrets | CommittedMaps: ...


class ReviewSecrets(Node):
    """User reviews secret findings."""

    scan: Annotated[SecretScanResult, Recall()]
    approved: SecretsGate

    async def __call__(self) -> CommittedMaps | None: ...


class CommitMaps(Node):
    """Commit the generated maps."""

    async def __call__(self) -> MappingDone: ...


CommittedMaps = Annotated[CommitMaps, Effect(vcs_commit_maps)]


class MappingDone(Node):
    """Terminal: mapping complete."""

    summary: str

    async def __call__(self) -> None: ...


map_codebase = Graph(start=InitMapCodebase)
