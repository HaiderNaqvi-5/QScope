"""Read-only, project-contained SQLite integrity checks."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

MAX_DATABASE_BYTES = 2 * 1024 * 1024 * 1024


def validate_database_path(project_root: Path, relative_path: str) -> Path:
    root = project_root.resolve()
    path = (root / relative_path).resolve()
    if path == root or root not in path.parents:
        raise ValueError("Database path must remain inside the selected project")
    if not path.is_file() or path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise ValueError("Database path must identify an existing SQLite file")
    if path.stat().st_size > MAX_DATABASE_BYTES:
        raise ValueError("Database exceeds the 2 GiB local integrity-check limit")
    return path


def inspect_sqlite_read_only(project_root: Path, relative_path: str) -> list[dict[str, Any]]:
    path = validate_database_path(project_root, relative_path)
    uri = f"file:{path.as_posix()}?mode=ro"
    checks: list[dict[str, Any]] = []
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        quick_rows = [str(row[0]) for row in connection.execute("PRAGMA quick_check(100)").fetchall()]
        checks.append({"name": "SQLite structural integrity", "status": "PASSED" if quick_rows == ["ok"] else "FAILED",
                       "severity": "CRITICAL", "evidence": {"quick_check": quick_rows[:100]}})
        foreign_rows = connection.execute("PRAGMA foreign_key_check").fetchmany(1001)
        truncated = len(foreign_rows) > 1000
        foreign_rows = foreign_rows[:1000]
        checks.append({"name": "Foreign-key and orphan integrity", "status": "FAILED" if foreign_rows else "PASSED",
                       "severity": "HIGH", "evidence": {
                           "violations": [{"table": row[0], "rowid": row[1], "parent": row[2], "constraint": row[3]}
                                          for row in foreign_rows], "truncated": truncated}})
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchmany(10_001)]
        checks.append({"name": "Database schema inventory", "status": "PASSED",
                       "severity": "INFO", "evidence": {"table_count": len(tables), "tables": tables[:10_000],
                                                           "truncated": len(tables) > 10_000}})
    finally:
        connection.close()
    return checks
