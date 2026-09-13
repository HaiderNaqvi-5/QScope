"""Dependency inventory tests."""
import json

from app.services.discovery import discover_project


def test_package_dependencies_are_inventoried(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"dependencies": {"fastify": "^4.0.0"}}))
    _, model = discover_project(str(tmp_path))
    assert {"name": "fastify", "version": "^4.0.0", "manifest": "package.json"} in model["dependencies"]


def test_requirements_dependencies_are_inventoried(tmp_path):
    (tmp_path / "requirements.txt").write_text("httpx==0.27.0\n# ignored\n-r dev.txt\n")
    _, model = discover_project(str(tmp_path))
    assert model["dependencies"] == [{"name": "httpx", "version": "0.27.0", "manifest": "requirements.txt"}]
