"""Shared Dep and Effect functions for work graphs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from bae import Dep, Effect

from bae.work.models import (
    BrownfieldResult,
    ExistingMaps,
    PlanTask,
    ProjectState,
    RoadmapData,
    SecretScanResult,
)


def load_state() -> ProjectState:
    """Load project state from .planning/config.json."""
    config_path = Path.cwd() / ".planning" / "config.json"
    if config_path.exists():
        data = json.loads(config_path.read_text())
        return ProjectState(
            root=Path.cwd(),
            phase=data.get("current_phase"),
            status=data.get("status", "active"),
        )
    return ProjectState(root=Path.cwd(), phase=None, status="unknown")


def load_roadmap() -> RoadmapData:
    """Load roadmap from .planning/ROADMAP.md (parsed as structured data)."""
    roadmap_path = Path.cwd() / ".planning" / "ROADMAP.md"
    if roadmap_path.exists():
        # Minimal parse -- real implementation reads markdown structure
        return RoadmapData(phases=[], current_phase=0)
    return RoadmapData(phases=[], current_phase=0)


async def git_commit(message: str, files: list[str]) -> str:
    """Stage files and create a git commit."""
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "git",
        "add",
        *files,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    proc = await asyncio.create_subprocess_exec(
        "git",
        "commit",
        "-m",
        message,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()


async def scan_secrets(paths: list[str] | None = None) -> SecretScanResult:
    """Scan paths for secrets/credentials."""
    # Stub -- real implementation runs a secret scanner
    return SecretScanResult(clean=True, findings=[])


def discover_plans(phase_id: str | None = None) -> list[PlanTask]:
    """Discover plan files for a phase."""
    plans_dir = Path.cwd() / ".planning" / "phases"
    if not plans_dir.exists():
        return []
    tasks: list[PlanTask] = []
    # Walk phase directories looking for PLAN.md files
    for plan_file in sorted(plans_dir.rglob("*-PLAN.md")):
        name = plan_file.stem
        parts = name.split("-")
        wave = 1
        if len(parts) >= 2 and parts[1].isdigit():
            wave = int(parts[1])
        tasks.append(
            PlanTask(
                plan_id=name,
                content=plan_file.read_text(),
                wave=wave,
            )
        )
    return tasks


def check_existing() -> ExistingMaps:
    """Check if codebase maps already exist."""
    maps_dir = Path.cwd() / ".planning" / "codebase"
    if maps_dir.exists():
        paths = [str(p) for p in maps_dir.glob("*.md")]
        return ExistingMaps(found=bool(paths), paths=paths)
    return ExistingMaps(found=False)


def detect_brownfield() -> BrownfieldResult:
    """Detect if current directory is a brownfield project."""
    # Stub -- checks for common project indicators
    return BrownfieldResult()


StateDep = Annotated[ProjectState, Dep(load_state)]
RoadmapDep = Annotated[RoadmapData, Dep(load_roadmap)]
BrownfieldDep = Annotated[BrownfieldResult, Dep(detect_brownfield)]


# -- Effect functions ---------------------------------------------------------


async def vcs_commit_quick(node) -> None:
    """Commit quick task changes."""
    await git_commit(node.commit_message, node.execution.files_changed)


async def vcs_commit_maps(node) -> None:
    """Commit generated codebase maps."""
    await git_commit("docs: map codebase", [".planning/codebase/"])


async def save_plan(node) -> None:
    """Write final plan to disk."""
    plan_dir = Path.cwd() / ".planning"
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "PLAN.md").write_text(node.plan.plan_content)


async def save_project(node) -> None:
    """Write PROJECT.md from synthesized context."""
    project_dir = Path.cwd() / ".planning"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "PROJECT.md").write_text(
        f"# {node.name}\n\n{node.description}\n\nStack: {', '.join(node.stack)}\n"
    )


async def save_roadmap(node) -> None:
    """Write or update roadmap file."""
    roadmap_dir = Path.cwd() / ".planning"
    roadmap_dir.mkdir(parents=True, exist_ok=True)
    phases_text = "\n".join(f"- Phase {i + 1}: {p}" for i, p in enumerate(node.phases))
    (roadmap_dir / "ROADMAP.md").write_text(f"# Roadmap\n\n{phases_text}\n")


async def save_roadmap_status(node) -> None:
    """Update roadmap with verification status."""
    roadmap_path = Path.cwd() / ".planning" / "ROADMAP.md"
    if roadmap_path.exists():
        content = roadmap_path.read_text()
        status = "PASSED" if node.verification.goal_met else "GAPS"
        content += f"\n\n## Verification: {status}\n"
        if node.verification.gaps:
            for gap in node.verification.gaps:
                content += f"- {gap}\n"
        roadmap_path.write_text(content)
