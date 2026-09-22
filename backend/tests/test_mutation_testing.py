import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.mutation_testing import parse_mutation_output, run_mutation_analysis


def test_mutation_summary_keeps_test_strength_separate_from_coverage():
    result = parse_mutation_output("Killed: 8\nSurvived: 2\nTimeout: 0")
    assert result["mutation_score"] == 80.0
    assert result["survived"] == 2


@pytest.mark.asyncio
async def test_unsupported_project_is_explicitly_not_applicable(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")
    result = await run_mutation_analysis(tmp_path, "AUTO", 10)
    assert result["status"] == "NOT_APPLICABLE"


def test_mutation_api_persists_not_applicable_result(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        response = client.post(f"/api/projects/{project['id']}/mutation/run", json={})
        assert response.status_code == 200
        assert response.json()["status"] == "NOT_APPLICABLE"
        cases = client.get(f"/api/projects/{project['id']}/generated-tests").json()
        assert any(case["category"] == "MUTATION" and case["status"] == "NOT_APPLICABLE" for case in cases)
