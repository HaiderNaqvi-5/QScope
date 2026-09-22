"""Typed metadata and preflight results for local analysis tools."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Availability(StrEnum):
    READY = "READY"
    MISSING = "MISSING"
    INCOMPATIBLE_VERSION = "INCOMPATIBLE_VERSION"
    ERROR = "ERROR"
    OPTIONAL_NOT_INSTALLED = "OPTIONAL_NOT_INSTALLED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    display_name: str
    executable: str
    version_args: tuple[str, ...]
    categories: tuple[str, ...]
    ecosystems: tuple[str, ...] = ()
    required: bool = False
    install_guidance: str = ""
    license: str = "Open source; verify the installed distribution's license."
    timeout_seconds: int = 300
    output_formats: tuple[str, ...] = ("text",)
    adapter: str = "universal"

