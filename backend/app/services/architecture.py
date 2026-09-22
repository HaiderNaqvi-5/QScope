"""Build an evidence-backed project topology from discovery output."""
from __future__ import annotations

import hashlib
from typing import Any


def build_architecture_map(project_model: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = [{"id": "project", "kind": "PROJECT", "label": "Project", "evidence": []}]
    edges: list[dict[str, Any]] = []

    def add(kind: str, item: dict[str, Any], relation: str = "CONTAINS") -> str:
        value = str(item.get("value", "unknown"))
        evidence = sorted(str(path) for path in item.get("evidence", []))
        node_id = hashlib.sha256(f"{kind}|{value}|{'|'.join(evidence)}".encode()).hexdigest()[:16]
        nodes.append({"id": node_id, "kind": kind, "label": value,
                      "confidence": item.get("confidence", "medium"), "evidence": evidence})
        edges.append({"source": "project", "target": node_id, "relation": relation})
        return node_id

    frontends = [add("FRONTEND", item) for item in project_model.get("frontend_targets", [])]
    backends = [add("BACKEND", item) for item in project_model.get("backend_targets", [])]
    services = [add("SERVICE", item) for item in project_model.get("services", [])]
    apis = [add("API", item, "EXPOSES") for item in
            [*project_model.get("api_specs", []), *project_model.get("graphql_specs", [])]]
    databases = [add("DATABASE", item, "USES") for item in project_model.get("database_indicators", [])]
    for frontend in frontends:
        for api in apis:
            edges.append({"source": frontend, "target": api, "relation": "CALLS"})
    for backend in [*backends, *services]:
        for api in apis:
            edges.append({"source": backend, "target": api, "relation": "IMPLEMENTS"})
        for database in databases:
            edges.append({"source": backend, "target": database, "relation": "READS_WRITES"})
    return {"nodes": nodes, "edges": edges}
