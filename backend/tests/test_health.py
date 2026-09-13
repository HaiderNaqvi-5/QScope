"""Health endpoint tests."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Test health endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "message" in data


def test_health_endpoint_accessible():
    """Test health endpoint is accessible."""
    response = client.get("/api/health")
    assert response.status_code in [200, 307]  # 307 for redirect or 200 for direct
