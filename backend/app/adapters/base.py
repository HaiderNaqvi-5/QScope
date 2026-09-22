"""Stable adapter contracts shared by all analyzer ecosystems."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class DetectionResult:
    applicable: bool
    evidence: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class ToolRequirement:
    tool_id: str
    required: bool = False
    reason: str = ""


@dataclass(frozen=True)
class AdapterTask:
    id: str
    tool: str
    argv: tuple[str, ...]
    working_directory: str = "."
    metadata: dict[str, Any] = field(default_factory=dict)


class AnalyzerAdapter(Protocol):
    id: str
    display_name: str

    def detect(self, project_model: dict[str, Any]) -> DetectionResult: ...
    def preflight(self, project_model: dict[str, Any]) -> list[ToolRequirement]: ...
    def plan(self, project_model: dict[str, Any], scan_mode: str) -> list[AdapterTask]: ...
    def normalize(self, raw_result: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]: ...

