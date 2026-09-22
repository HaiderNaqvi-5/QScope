import time

from fastapi.testclient import TestClient
import app.api.routes.remediation as remediation_routes

from app.main import app


def _finding(client, tmp_path):
    (tmp_path / "app.py").write_text("print('debug')\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='1'\n")
    project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
    scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
    for _ in range(100):
        state = client.get(f"/api/scans/{scan['id']}").json()
        if state["status"] in {"COMPLETED", "FAILED", "ERROR"}:
            break
        time.sleep(0.03)
    finding = client.get(f"/api/scans/{scan['id']}/findings").json()[0]
    return project, finding


def _request(finding_id, **overrides):
    body = {
        "mode": "ASSISTED", "reproduced": False, "deterministic_static_evidence": True,
        "impact_radius": {"files": ["app.py"], "shared": False},
        "plan": {"finding_ids": [finding_id], "root_cause": "Debug statement remains",
                 "proposed_strategy": "Remove the debug statement", "expected_files": ["app.py"],
                 "expected_tests": ["python compile"], "expected_behavior_after_fix": "No debug output",
                 "risk": "SAFE", "fix_confidence": 0.96},
    }
    body.update(overrides)
    return body


def test_remediation_plan_is_durable_and_defaults_to_assisted(tmp_path):
    with TestClient(app) as client:
        project, finding = _finding(client, tmp_path)
        before_score = client.get(f"/api/scans/{finding['scan_id']}/report").json()["score"]
        response = client.post(f"/api/findings/{finding['id']}/remediations/plan",
                               json=_request(finding["id"]))
        assert response.status_code == 201
        attempt = response.json()
        assert attempt["mode"] == "ASSISTED"
        assert attempt["status"] == "PLAN_VALIDATED"
        assert attempt["eligibility"]["action"] == "ASSISTED"
        assert attempt["finding_confidence"] == finding["confidence"]
        listing = client.get(f"/api/projects/{project['id']}/remediations").json()
        assert [item["id"] for item in listing] == [attempt["id"]]
        assert client.get(f"/api/remediations/{attempt['id']}").json()["plan"]["root_cause"]
        patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-print('debug')\n+print('ready')\n"
        submitted = client.post(f"/api/remediations/{attempt['id']}/patch", json={"patch": patch})
        assert submitted.json()["status"] == "PATCH_VALIDATED"
        denied = client.post(f"/api/remediations/{attempt['id']}/apply", json={"approved": False})
        assert denied.status_code == 409
        applied = client.post(f"/api/remediations/{attempt['id']}/apply", json={"approved": True})
        assert applied.status_code == 200
        assert applied.json()["status"] == "FIX_APPLIED_PENDING_VERIFICATION"
        assert applied.json()["final_outcome"] is None
        assert applied.json()["checkpoint"]["files"]["app.py"]["content_base64"]
        assert (tmp_path / "app.py").read_text() == "print('ready')\n"
        check = {"name": "Python syntax", "argv": ["python", "-m", "py_compile", "app.py"]}
        verified = client.post(f"/api/remediations/{attempt['id']}/verify",
                               json={"original": check, "targeted": [check], "regression": [check]})
        assert verified.status_code == 200
        assert verified.json()["status"] == "VERIFIED_FIXED"
        assert verified.json()["evidence"]["original_retest"]["status"] == "PASSED"
        assert client.get(f"/api/findings/{finding['id']}").json()["status"] == "VERIFIED_FIXED"
        report = client.get(f"/api/scans/{finding['scan_id']}/report").json()
        assert report["findings"][0]["status"] == "VERIFIED_FIXED"
        assert report["findings"][0]["baseline_state"] == "NEW"
        assert report["score"] >= before_score
        assert report["remediation_verified"] == 1
        assert report["remediations"][0]["final_outcome"] == "VERIFIED_FIXED"


def test_api_reproduction_is_qsscope_owned_and_required_for_reproduced_plan(tmp_path, monkeypatch):
    class Response:
        status_code = 200

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, headers):
            assert method == "GET"
            assert url == "http://127.0.0.1:8123/orders/other-user"
            assert "authorization" not in {key.lower() for key in headers}
            return Response()

    monkeypatch.setattr(remediation_routes.httpx, "AsyncClient", Client)
    with TestClient(app) as client:
        _project, finding = _finding(client, tmp_path)
        replay = client.post(f"/api/findings/{finding['id']}/remediations/reproduce", json={
            "base_url": "http://127.0.0.1:8123", "method": "GET", "endpoint": "/orders/other-user",
            "expected_status_codes": [403, 404], "headers": {"Authorization": "must-not-persist"},
        })
        assert replay.status_code == 200
        assert replay.json() == {"status": "REPRODUCED", "method": "GET", "endpoint": "/orders/other-user",
                                 "expected_status_codes": [403, 404], "actual_status": 200}
        body = _request(finding["id"], reproduced=True, deterministic_static_evidence=False)
        attempt = client.post(f"/api/findings/{finding['id']}/remediations/plan", json=body)
        assert attempt.status_code == 201
        assert attempt.json()["reproduced"] is True
        assert attempt.json()["evidence"]["reproduction"]["actual_status"] == 200


def test_reproduced_flag_without_qsscope_replay_does_not_make_plan_eligible(tmp_path):
    with TestClient(app) as client:
        _project, finding = _finding(client, tmp_path)
        body = _request(finding["id"], reproduced=True, deterministic_static_evidence=False)
        attempt = client.post(f"/api/findings/{finding['id']}/remediations/plan", json=body)
        assert attempt.status_code == 201
        assert attempt.json()["reproduced"] is False
        assert attempt.json()["status"] == "MANUAL_REVIEW_REQUIRED"


def test_unconfirmed_remediation_is_manual_review_only(tmp_path):
    with TestClient(app) as client:
        _project, finding = _finding(client, tmp_path)
        body = _request(finding["id"], mode="AUTONOMOUS", deterministic_static_evidence=False)
        response = client.post(f"/api/findings/{finding['id']}/remediations/plan", json=body)
        assert response.status_code == 201
        assert response.json()["status"] == "MANUAL_REVIEW_REQUIRED"
        assert response.json()["eligibility"]["eligible"] is False


def test_patch_cannot_expand_beyond_validated_plan(tmp_path):
    with TestClient(app) as client:
        _project, finding = _finding(client, tmp_path)
        attempt = client.post(f"/api/findings/{finding['id']}/remediations/plan",
                              json=_request(finding["id"])).json()
        patch = "--- /dev/null\n+++ b/unplanned.py\n@@ -0,0 +1 @@\n+value = 1\n"
        response = client.post(f"/api/remediations/{attempt['id']}/patch", json={"patch": patch})
        assert response.status_code == 200
        assert response.json()["status"] == "PATCH_REJECTED"
        assert "outside the validated remediation plan" in response.json()["evidence"]["patch_preflight"]["reasons"][-1]


def test_plan_must_name_requested_finding(tmp_path):
    with TestClient(app) as client:
        _project, finding = _finding(client, tmp_path)
        body = _request(finding["id"])
        body["plan"]["finding_ids"] = ["different"]
        response = client.post(f"/api/findings/{finding['id']}/remediations/plan", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["message"] == "Remediation plan must include the requested finding"


def test_failed_verification_rolls_back_and_stops_after_two_attempts(tmp_path):
    with TestClient(app) as client:
        _project, finding = _finding(client, tmp_path)
        broken_patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-print('debug')\n+print(\n"
        check = {"name": "Original syntax reproduction", "argv": ["python", "-m", "py_compile", "app.py"]}
        for expected_number in (1, 2):
            attempt = client.post(f"/api/findings/{finding['id']}/remediations/plan",
                                  json=_request(finding["id"])).json()
            assert attempt["attempt_number"] == expected_number
            assert client.post(f"/api/remediations/{attempt['id']}/patch",
                               json={"patch": broken_patch}).json()["status"] == "PATCH_VALIDATED"
            assert client.post(f"/api/remediations/{attempt['id']}/apply",
                               json={"approved": True}).json()["status"] == "FIX_APPLIED_PENDING_VERIFICATION"
            verified = client.post(f"/api/remediations/{attempt['id']}/verify",
                                   json={"original": check, "targeted": [check]}).json()
            assert verified["status"] == "ROLLED_BACK"
            assert verified["final_outcome"] == "FIX_FAILED"
            assert (tmp_path / "app.py").read_text() == "print('debug')\n"
        third = client.post(f"/api/findings/{finding['id']}/remediations/plan",
                            json=_request(finding["id"]))
        assert third.status_code == 409
        assert "attempt limit" in third.json()["error"]["message"]


def test_remediation_queue_exposes_required_metadata_and_disposition(tmp_path):
    with TestClient(app) as client:
        project, finding = _finding(client, tmp_path)
        attempt = client.post(f"/api/findings/{finding['id']}/remediations/plan",
                              json=_request(finding["id"])).json()
        queue = client.get(f"/api/projects/{project['id']}/remediation-queue")
        assert queue.status_code == 200
        item = queue.json()[0]
        assert item["finding_title"] == finding["title"]
        assert item["severity"] == finding["severity"]
        assert item["affected_files"] == ["app.py"]
        assert item["verification_test_count"] == 2
        assert {"PREVIEW_FIX", "SKIP", "MANUAL_REVIEW"} <= set(item["available_actions"])
        skipped = client.post(f"/api/remediations/{attempt['id']}/disposition",
                              json={"disposition": "SKIPPED", "note": "defer"})
        assert skipped.json()["status"] == "SKIPPED"
        assert skipped.json()["evidence"]["disposition"]["note"] == "defer"


def test_fix_safe_queue_applies_and_verifies_each_unit(tmp_path):
    with TestClient(app) as client:
        project, finding = _finding(client, tmp_path)
        body = _request(finding["id"], mode="AUTONOMOUS")
        attempt = client.post(f"/api/findings/{finding['id']}/remediations/plan", json=body).json()
        patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-print('debug')\n+print('ready')\n"
        assert client.post(f"/api/remediations/{attempt['id']}/patch",
                           json={"patch": patch}).json()["status"] == "PATCH_VALIDATED"
        check = {"name": "Python syntax", "argv": ["python", "-m", "py_compile", "app.py"]}
        response = client.post(f"/api/projects/{project['id']}/remediation-queue/fix-safe", json={
            "entries": [{"attempt_id": attempt["id"],
                         "verification": {"original": check, "targeted": [check], "regression": [check]}}],
        })
        assert response.status_code == 200
        assert response.json()["processed"] == response.json()["verified"] == 1
        assert response.json()["attempts"][0]["status"] == "VERIFIED_FIXED"
        assert (tmp_path / "app.py").read_text() == "print('ready')\n"
