"""Path policy and data directory management.

Ensures all paths are contained within safe boundaries.
"""
from pathlib import Path
from app.core.config import settings


def get_data_dir() -> Path:
    """Get the QSScope data directory."""
    return settings.data_dir


def get_projects_dir() -> Path:
    """Get the projects subdirectory."""
    projects_dir = get_data_dir() / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    return projects_dir


def get_scans_dir() -> Path:
    """Get the scans subdirectory."""
    scans_dir = get_data_dir() / "artifacts"
    scans_dir.mkdir(parents=True, exist_ok=True)
    return scans_dir


def get_reports_dir() -> Path:
    """Get the reports subdirectory."""
    reports_dir = get_data_dir() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def get_baselines_dir() -> Path:
    """Get the baselines subdirectory."""
    baselines_dir = get_data_dir() / "baselines"
    baselines_dir.mkdir(parents=True, exist_ok=True)
    return baselines_dir


def get_screenshots_dir() -> Path:
    """Get the screenshots subdirectory."""
    screenshots_dir = get_data_dir() / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    return screenshots_dir


def get_logs_dir() -> Path:
    """Get the logs subdirectory."""
    logs_dir = get_data_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_temp_dir() -> Path:
    """Get the temporary subdirectory."""
    temp_dir = get_data_dir() / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def is_path_safe(path: Path, base: Path | None = None) -> bool:
    """Check if a path is contained within the safe base directory.
    
    Args:
        path: Path to validate
        base: Base directory (defaults to project root)
    
    Returns:
        True if path is contained within base, False otherwise
    """
    if base is None:
        base = Path.cwd()
    
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False
