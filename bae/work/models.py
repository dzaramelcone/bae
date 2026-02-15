"""Shared Pydantic models for work graphs."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class ProjectState(BaseModel):
    root: Path
    phase: str | None
    status: str


class RoadmapData(BaseModel):
    phases: list[dict]
    current_phase: int


class PlanConfig(BaseModel):
    """Typed config bag -- safe for Recall (unique type)."""

    skip_research: bool = False
    max_revisions: int = 3


class PlanTask(BaseModel):
    plan_id: str
    content: str
    wave: int
    autonomous: bool = True


class ExecutionResult(BaseModel):
    plan_id: str
    success: bool
    errors: list[str] = []


class WaveResult(BaseModel):
    wave_number: int
    results: list[ExecutionResult]
    all_passed: bool


class SecretScanResult(BaseModel):
    clean: bool
    findings: list[str]


class MapperResult(BaseModel):
    focus: str  # tech | arch | quality | concerns
    documents: list[str]
    line_counts: dict[str, int]


class TaskDescription(BaseModel):
    """Wrapper for str -- gives Recall a unique type to find."""

    text: str


class ExistingMaps(BaseModel):
    found: bool
    paths: list[str] = []


class BrownfieldResult(BaseModel):
    is_brownfield: bool = False
    existing_stack: list[str] = []


class ResearchFinding(BaseModel):
    area: str
    summary: str
    recommendations: list[str]
