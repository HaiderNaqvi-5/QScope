from types import SimpleNamespace
import asyncio
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import AsyncSessionLocal
from app.main import app
from app.models import Finding
from app.services.fix_packs import validate_fix_pack


def test_fix_pack_requires_strong_shared_root_cause_and_every_member_scenario():
    findings = [SimpleNamespace(id=f"f-{index}", correlation_key="root-owner-check") for index in range(3)]
    scenarios = {item.id: [{"name": "replay"}] for item in findings}
    assert validate_fix_pack(findings, "root-owner-check", 0.95, scenarios) == []
    weak = validate_fix_pack(findings, "root-owner-check", 0.7, scenarios)
    assert "at least 0.90" in weak[0]
    mismatch = [*findings[:2], SimpleNamespace(id="f-3", correlation_key="different")]
    assert any("share" in reason for reason in validate_fix_pack(
        mismatch, "root-owner-check", 0.95, scenarios))
    assert any("f-2" in reason for reason in validate_fix_pack(
        findings, "root-owner-check", 0.95, {"f-0": [{}], "f-1": [{}]}))


def test_fix_pack_api_persists_three_strongly_correlated_members(tmp_path):
    with TestClient(app) as client:
        project = client.post("/api/projects/discover", json={"root_path": str(tmp_path)}).json()
        scan = client.post(f"/api/projects/{project['id']}/scans", json={"mode": "QUICK"}).json()
        for _ in range(200):
            state = client.get(f"/api/scans/{scan['id']}").json()
            if state["status"] in {"COMPLETED", "FAILED", "ERROR"}:
                break
            time.sleep(0.03)
        ids = [str(uuid4()) for _ in range(3)]

        async def seed():
            async with AsyncSessionLocal() as db:
                db.add_all([Finding(id=finding_id, scan_id=scan["id"], title=f"Owner failure {index}",
                    severity="HIGH", tool="fixture", stage="LOGICAL_TESTING", message="Cross-owner allowed",
                    category="SECURITY", subcategory="AUTHORIZATION", confidence="0.99",
                    evidence={}, sources=[], fingerprint=f"fp-{finding_id}", correlation_key="owner-root",
                    status="OPEN") for index, finding_id in enumerate(ids)])
                await db.commit()
        asyncio.run(seed())
        check = {"name": "ownership replay", "argv": ["python", "-c", "raise SystemExit(0)"]}
        payload = {"root_cause_id": "owner-root", "finding_ids": ids, "correlation_confidence": 0.97,
                   "proposed_shared_correction": "Centralize ownership enforcement", "risk": "MODERATE",
                   "impact_radius": {"files": ["auth.py"], "routes": ["orders"]},
                   "verification_scenarios": {finding_id: [check] for finding_id in ids}}
        created = client.post(f"/api/projects/{project['id']}/fix-packs", json=payload)
        assert created.status_code == 201
        assert created.json()["finding_ids"] == ids
        assert created.json()["correlation_confidence"] == 0.97
        listing = client.get(f"/api/projects/{project['id']}/fix-packs")
        assert listing.status_code == 200
        assert listing.json()[0]["root_cause_id"] == "owner-root"
        report = client.get(f"/api/scans/{scan['id']}/report").json()
        assert report["fix_pack_count"] == 1
        assert report["fix_packs"][0]["finding_ids"] == ids
