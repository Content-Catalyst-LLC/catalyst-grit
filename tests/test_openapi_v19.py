import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_openapi_matches_institutional_api_routes_and_security():
    spec = yaml.safe_load((ROOT / "openapi.yaml").read_text())
    assert spec["info"]["version"] == "1.9.0"
    assert spec["servers"][0]["url"] == "/v1"
    expected = {
        "/health",
        "/projects/{project_id}/records",
        "/records/{record_id}",
        "/records/{record_id}/revisions",
        "/records/{record_id}/actions",
        "/projects/{project_id}/checkpoints",
        "/records/{record_id}/reviews",
        "/projects/{project_id}/evidence",
        "/projects/{project_id}/patterns",
        "/projects/{project_id}/monitoring",
        "/projects/{project_id}/handoffs",
        "/projects/{project_id}/audit",
        "/publications",
    }
    assert set(spec["paths"]) == expected
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert spec["paths"]["/health"]["get"]["security"] == []
    assert spec["paths"]["/publications"]["post"]["x-required-scope"] == "publications:write"


def test_new_schemas_are_versioned_and_workspace_schema_exposes_governance():
    publication = json.loads((ROOT / "schemas/catalyst_grit_publication.schema.json").read_text())
    response = json.loads((ROOT / "schemas/catalyst_grit_api_response.schema.json").read_text())
    workspace = json.loads((ROOT / "schemas/catalyst_grit_workspace_bundle.schema.json").read_text())
    assert publication["x-catalyst-grit-version"] == response["x-catalyst-grit-version"] == "1.9.0"
    assert publication["properties"]["format"]["const"] == "catalyst-grit-publication/1.0"
    assert response["properties"]["contract"]["const"] == "catalyst-grit-api/1.0"
    for name in ("institutional_policies", "access_reviews", "publication_artifacts", "methodology_registry"):
        assert name in workspace["properties"]
