from fastapi.testclient import TestClient
import json

from app.main import app


def test_manual_case_crud_and_evidence(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        created = client.post("/api/manual-tests", json={
            "project_id": project["id"], "module": "Authentication", "feature": "Login",
            "preconditions": ["A local test user exists"], "steps": ["Open login", "Submit valid credentials"],
            "expected_result": "The project dashboard opens",
        })
        assert created.status_code == 201
        case = created.json()
        assert case["status"] == "NOT_RUN"
        updated = client.patch(f"/api/manual-tests/{case['id']}", json={
            "status": "FAIL", "severity": "HIGH", "actual_result": "Server returned 500",
        })
        assert updated.status_code == 200
        attached = client.post(f"/api/manual-tests/{case['id']}/evidence",
            files={"file": ("failure.png", b"not-a-real-secret", "image/png")})
        assert attached.status_code == 201
        assert len(attached.json()["sha256"]) == 64
        evidence = client.get(f"/api/manual-evidence/{attached.json()['id']}")
        assert evidence.status_code == 200
        assert evidence.content == b"not-a-real-secret"
        assert "failure.png" in evidence.headers["content-disposition"]
        listing = client.get(f"/api/projects/{project['id']}/manual-tests")
        assert listing.status_code == 200
        assert listing.json()[0]["actual_result"] == "Server returned 500"
        assert listing.json()[0]["evidence"][0]["original_name"] == "failure.png"
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        import time
        for _ in range(100):
            report = client.get(f"/api/scans/{scan['id']}/report")
            if report.json()["status"] in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(0.02)
        assert report.json()["manual_test_count"] == 1
        assert report.json()["manual_test_failures"] == 1
        markdown = client.get(f"/api/scans/{scan['id']}/report/export?format=markdown")
        assert "## Manual Testing" in markdown.text
        assert "Authentication" in markdown.text
        assert client.delete(f"/api/manual-tests/{case['id']}").status_code == 204
        assert client.get(f"/api/projects/{project['id']}/manual-tests").json() == []


def test_failed_manual_case_requires_severity(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        response = client.post("/api/manual-tests", json={"project_id": project["id"], "module": "Checkout",
            "steps": ["Submit"], "expected_result": "Order saved", "status": "FAIL"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_manual_evidence_rejects_unsafe_type(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        case = client.post("/api/manual-tests", json={"project_id": project["id"], "module": "UI",
            "steps": ["Inspect"], "expected_result": "Looks correct"}).json()
        response = client.post(f"/api/manual-tests/{case['id']}/evidence",
            files={"file": ("payload.exe", b"MZ", "application/octet-stream")})
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Unsupported evidence type"


def test_deterministic_frontend_checklist_is_draft_idempotent_and_includes_manual_a11y(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"react": "18.2.0"}}))
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        first = client.post(f"/api/projects/{project['id']}/manual-tests/derive")
        second = client.post(f"/api/projects/{project['id']}/manual-tests/derive")
        assert first.status_code == 200
        assert len(first.json()) == len(second.json()) == 4
        assert all(not case["accepted"] and case["source"] == "DETERMINISTIC_GENERATED_DRAFT"
                   for case in first.json())
        features = {case["feature"] for case in first.json()}
        assert {"Keyboard navigation", "Screen-reader semantics", "Mobile navigation and actions"} <= features
