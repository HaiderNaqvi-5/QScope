"""Health endpoint tests."""
import logging

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.logging import JSONFormatter

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


def test_json_formatter_handles_standard_log_records():
    formatted = JSONFormatter().format(logging.LogRecord(
        "test", logging.INFO, __file__, 1, "hello", (), None,
    ))
    assert '"message": "hello"' in formatted
