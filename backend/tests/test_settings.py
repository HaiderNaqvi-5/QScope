"""Settings endpoint tests."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_get_settings():
    """Test getting settings."""
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "debug" in data
    assert "log_level" in data
    assert "enable_llm_features" in data


def test_update_settings():
    """Test updating settings."""
    response = client.patch("/api/settings", json={"debug": True})
    assert response.status_code == 200
    data = response.json()
    assert data["debug"] is True
