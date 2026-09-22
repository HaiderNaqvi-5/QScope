import sqlite3
import time

from fastapi.testclient import TestClient

from app.main import app
from app.services.data_integrity import inspect_sqlite_read_only


def _orphan_database(path):
    connection = sqlite3.connect(path)
    connection.executescript("""
    PRAGMA foreign_keys=OFF;
    CREATE TABLE parent (id INTEGER PRIMARY KEY);
    CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id));
    INSERT INTO child(id, parent_id) VALUES (1, 999);
    """)
    connection.commit()
    connection.close()


def test_sqlite_integrity_is_read_only_and_detects_orphan(tmp_path):
    database = tmp_path / "fixture.db"
    _orphan_database(database)
    before = database.read_bytes()
    checks = inspect_sqlite_read_only(tmp_path, "fixture.db")
    assert next(item for item in checks if item["name"].startswith("SQLite"))["status"] == "PASSED"
    foreign = next(item for item in checks if item["name"].startswith("Foreign"))
    assert foreign["status"] == "FAILED"
    assert foreign["evidence"]["violations"][0]["parent"] == "parent"
    assert database.read_bytes() == before


def test_data_integrity_api_persists_cases_and_finding(tmp_path):
    _orphan_database(tmp_path / "fixture.db")
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(100):
            state = client.get(f"/api/scans/{scan['id']}").json()
            if state["status"] in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(0.03)
        response = client.post(f"/api/projects/{project['id']}/data-integrity/run",
                               json={"database_path": "fixture.db", "scan_id": scan["id"]})
        assert response.status_code == 200
        assert response.json()["total"] == 3
        assert response.json()["failed"] == 1
        findings = client.get(f"/api/scans/{scan['id']}/findings").json()
        assert any(item["subcategory"] == "DATA_INTEGRITY" and item["severity"] == "HIGH" for item in findings)


def test_data_integrity_rejects_outside_project(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        response = client.post(f"/api/projects/{project['id']}/data-integrity/run",
                               json={"database_path": "../outside.db"})
        assert response.status_code == 422
