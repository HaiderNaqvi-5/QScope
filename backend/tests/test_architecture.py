from app.services.architecture import build_architecture_map


def test_full_stack_topology_links_frontend_backend_api_and_database():
    model = {
        "frontend_targets": [{"value": "Next.js", "evidence": ["frontend/package.json"], "confidence": "high"}],
        "backend_targets": [{"value": "FastAPI", "evidence": ["backend/app/main.py"], "confidence": "high"}],
        "api_specs": [{"value": "OpenAPI", "evidence": ["openapi.json"], "confidence": "high"}],
        "database_indicators": [{"value": "SQLite", "evidence": ["app.db"], "confidence": "high"}],
    }
    topology = build_architecture_map(model)
    kinds = {node["kind"] for node in topology["nodes"]}
    relations = {edge["relation"] for edge in topology["edges"]}
    assert {"PROJECT", "FRONTEND", "BACKEND", "API", "DATABASE"} <= kinds
    assert {"CALLS", "IMPLEMENTS", "READS_WRITES"} <= relations
    assert all(node.get("evidence") is not None for node in topology["nodes"])
