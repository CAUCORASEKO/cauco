from fastapi.testclient import TestClient


def test_tool_catalog_endpoints_are_deterministic_and_non_executable(client: TestClient) -> None:
    listed = client.get("/api/tools")
    detail = client.get("/api/tools/git")
    categories = client.get("/api/tools/categories")
    operations = client.get("/api/tools/git/operations")

    assert listed.status_code == 200
    assert listed.json()["count"] == 7
    assert [tool["id"] for tool in listed.json()["tools"]] == sorted(
        tool["id"] for tool in listed.json()["tools"]
    )
    assert detail.json()["execution_enabled"] is False
    assert all(not operation["execution_enabled"] for operation in operations.json()["operations"])
    assert categories.json()["categories"] == sorted(categories.json()["categories"])


def test_tool_validation_reports_flags_without_execution(client: TestClient) -> None:
    status = client.post("/api/tools/validate", json={"tool_id": "git", "operation_id": "status"})
    reset = client.post(
        "/api/tools/validate", json={"tool_id": "git", "operation_id": "reset_hard"}
    )
    missing = client.post("/api/tools/validate", json={"tool_id": "missing", "operation_id": "run"})

    assert status.json()["valid"] is True
    assert status.json()["safe"] is True
    assert status.json()["confirmation_required"] is False
    assert status.json()["execution_enabled"] is False
    assert reset.json()["valid"] is False
    assert reset.json()["operation_enabled"] is False
    assert missing.json()["tool_exists"] is False
    assert client.get("/api/tools/missing").status_code == 404


def test_agent_plan_and_approved_review_expose_tool_readiness(client: TestClient) -> None:
    planned = client.post("/api/agents/plan", json={"instruction": "Review the Git diff"})
    created = client.post("/api/agents/plan-reviews", json={"instruction": "Review the Git diff"})
    approved = client.post(
        f"/api/agents/plan-reviews/{created.json()['review_id']}/approve", json={}
    )

    assert planned.status_code == 200
    assert planned.json()["readiness"]["ready"] is True
    assert all(step["tool_reference"] for step in planned.json()["plan"]["steps"])
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["readiness"]["ready"] is True
    assert approved.json()["readiness"]["execution_enabled"] is False


def test_readiness_detects_missing_tool(client: TestClient) -> None:
    client.app.state.tool_registry._tools.pop("git")
    response = client.post("/api/agents/plan", json={"instruction": "Review the Git diff"})
    git_references = [
        item for item in response.json()["readiness"]["references"] if item["tool_id"] == "git"
    ]
    assert response.json()["readiness"]["ready"] is False
    assert git_references and all(not item["registered"] for item in git_references)
