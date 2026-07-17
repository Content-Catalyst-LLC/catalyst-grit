import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_openapi_matches_institutional_api_routes_and_security():
    spec = yaml.safe_load((ROOT / "openapi.yaml").read_text())
    assert spec["info"]["version"] == "2.0.0"
    assert spec["servers"][0]["url"] == "/"
    expected = {
        "/v1/health", "/v2/health",
        "/v1/projects/{project_id}/records", "/v1/records/{record_id}",
        "/v1/records/{record_id}/revisions", "/v1/records/{record_id}/actions",
        "/v1/projects/{project_id}/checkpoints", "/v1/records/{record_id}/reviews",
        "/v1/projects/{project_id}/evidence", "/v1/projects/{project_id}/patterns",
        "/v1/projects/{project_id}/monitoring", "/v1/projects/{project_id}/handoffs",
        "/v1/projects/{project_id}/audit", "/v1/publications",
        "/v2/projects/{project_id}/platform", "/v2/projects/{project_id}/workflows",
        "/v2/workflows", "/v2/workflows/{workflow_id}",
        "/v2/workflows/{workflow_id}/steps/{step_key}",
        "/v2/projects/{project_id}/connections",
        "/v2/projects/{project_id}/portable-snapshots",
    }
    assert set(spec["paths"]) == expected
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert spec["paths"]["/v2/health"]["get"]["security"] == []
    assert spec["paths"]["/v1/publications"]["post"]["x-required-scope"] == "publications:write"


def test_new_schemas_are_versioned_and_workspace_schema_exposes_governance():
    publication = json.loads((ROOT / "schemas/catalyst_grit_publication.schema.json").read_text())
    response = json.loads((ROOT / "schemas/catalyst_grit_api_response.schema.json").read_text())
    workspace = json.loads((ROOT / "schemas/catalyst_grit_workspace_bundle.schema.json").read_text())
    assert publication["x-catalyst-grit-version"] == response["x-catalyst-grit-version"] == "2.0.0"
    assert publication["properties"]["format"]["const"] == "catalyst-grit-publication/1.0"
    assert response["properties"]["contract"]["const"] == "catalyst-grit-api/2.0"
    for name in ("institutional_policies", "access_reviews", "publication_artifacts", "methodology_registry"):
        assert name in workspace["properties"]


def test_v2_openapi_exposes_connected_platform_scopes_and_schema():
    spec = yaml.safe_load((ROOT / "openapi.yaml").read_text())
    assert spec["paths"]["/v2/projects/{project_id}/platform"]["get"]["x-required-scope"] == "platform:read"
    assert spec["paths"]["/v2/workflows"]["post"]["x-required-scope"] == "platform:write"
    assert spec["paths"]["/v2/workflows/{workflow_id}/steps/{step_key}"]["post"]["x-required-scope"] == "platform:review"
    assert spec["paths"]["/v2/projects/{project_id}/portable-snapshots"]["post"]["x-required-scope"] == "platform:export"
    assert spec["components"]["schemas"]["ConnectedPlatform"]["$ref"].endswith("catalyst_grit_connected_platform.schema.json")
