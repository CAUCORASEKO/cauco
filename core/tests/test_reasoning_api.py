from collections.abc import Iterator
from pathlib import Path

import pytest
from cauco_reasoning import (
    ReasoningProposal,
    ReasoningProposalStep,
    ReasoningRequest,
    ReasoningResult,
    ReasoningService,
)
from fastapi.testclient import TestClient

from cauco_core.ai.exceptions import ProviderUnavailableError
from cauco_core.ai.service import AIChatResult
from cauco_core.config import Settings
from cauco_core.main import create_app

CONVERSATION_ID = "00000000-0000-4000-8000-000000000001"
CONVERSATION_ID_TWO = "00000000-0000-4000-8000-000000000002"


class RecordingEngine:
    def __init__(self, result: ReasoningResult) -> None:
        self.result = result
        self.calls = 0

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.calls += 1
        return self.result


class RecordingAIService:
    def __init__(self, response: str = "", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = 0

    def chat(self, message: str, model: str | None = None, *, use_memory: bool = True) -> AIChatResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return AIChatResult(
            provider="fake",
            model="fake-model",
            response=self.response,
        )


@pytest.fixture
def reasoning_client(tmp_path: Path) -> Iterator[TestClient]:
    brain = tmp_path / "brain"
    brain.mkdir()
    (brain / "Tasks.md").write_text(
        "# Tasks\n\n## Current Priorities\n\n- Complete reasoning API.\n",
        encoding="utf-8",
    )
    (brain / "Projects.md").write_text(
        "# Projects\n\n## Active\n\n### Cauco\n\nReasoning architecture.\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with TestClient(create_app(Settings(brain_dir=brain, workspace_dir=workspace))) as client:
        original_post = client.post

        def post(url: str, *args, **kwargs):
            if url == "/api/reasoning/conversation/respond":
                payload = dict(kwargs.get("json", {}))
                payload.setdefault("conversation_id", CONVERSATION_ID)
                kwargs["json"] = payload
            return original_post(url, *args, **kwargs)

        client.post = post  # type: ignore[method-assign]
        yield client


def test_conversation_requires_a_valid_opaque_uuid(reasoning_client: TestClient) -> None:
    valid = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "What can you do?", "conversation_id": CONVERSATION_ID},
    )
    invalid = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "What can you do?", "conversation_id": "not-a-uuid"},
    )
    other = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "What can you do?", "conversation_id": CONVERSATION_ID_TWO},
    )
    assert valid.status_code == 200
    assert invalid.status_code == 422
    assert other.status_code == 200


def test_reasoning_defaults_false_and_normal_planning_works(
    reasoning_client: TestClient,
) -> None:
    engine = RecordingEngine(
        ReasoningResult(provider="test", model="m", text="unused", reasoning_performed=True)
    )
    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = (
        ReasoningService(engine)
    )

    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={"instruction": "Plan the next Cauco project task"},
    )

    assert response.status_code == 200
    assert response.json()["reasoning_requested"] is False
    assert response.json()["planning"]["status"] == "planned"
    assert engine.calls == 0


def test_conversation_executes_only_exact_workspace_reads(reasoning_client: TestClient) -> None:
    workspace = reasoning_client.app.state.workspace_policy.root
    (workspace / "notas.txt").write_text("hola", encoding="utf-8")

    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "Lee el archivo notas.txt."},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "hola"
    assert response.json()["execution_performed"] is True


def test_conversation_existing_workspace_write_keeps_review_without_mutation(
    reasoning_client: TestClient,
) -> None:
    workspace = reasoning_client.app.state.workspace_policy.root
    (workspace / "prueba.txt").write_text("original", encoding="utf-8")

    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "Crea un archivo prueba.txt con este contenido: hola."},
    )

    assert response.status_code == 200
    assert response.json()["planning_status"] == "pending_review"
    assert response.json()["review_id"]
    assert (workspace / "prueba.txt").read_text() == "original"


def test_reasoning_request_is_non_executing_and_preserves_caller_routing_inputs(
    reasoning_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = ReasoningProposal(
        summary="Use research",
        suggested_steps=(
            ReasoningProposalStep(
                "Research",
                suggested_agent_id="research",
                suggested_intent="provider-intent",
            ),
        ),
    )
    engine = RecordingEngine(
        ReasoningResult(
            provider="test",
            model="m",
            text="advice",
            reasoning_performed=True,
            proposal=proposal,
        )
    )
    orchestration = reasoning_client.app.state.reasoning_orchestration_service
    orchestration.reasoning_service = ReasoningService(engine)
    service = reasoning_client.app.state.reasoning_aware_planning_service
    original_plan = service.plan
    received = []

    def capture(request, **kwargs):
        received.append((request, kwargs))
        return original_plan(request, **kwargs)

    monkeypatch.setattr(service, "plan", capture)
    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={
            "instruction": "Analyze the Cauco project options",
            "intent": "caller-intent",
            "preferred_agent_id": "project",
            "use_reasoning": True,
        },
    )

    assert response.status_code == 200
    assert engine.calls == 1
    assert received[0][0].allow_execution is False
    assert received[0][0].preferred_agent_id == "project"
    assert received[0][0].intent == "caller-intent"
    assert received[0][1] == {"use_reasoning": True}
    payload = response.json()
    assert payload["proposal_validated"] is True
    assert payload["planning_context_enriched"] is True


def test_reasoning_api_rejects_allow_execution(reasoning_client: TestClient) -> None:
    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={"instruction": "Plan work", "allow_execution": True},
    )

    assert response.status_code == 422


def test_default_noop_reasoning_is_safe_when_explicitly_requested(
    reasoning_client: TestClient,
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={
            "instruction": "Analyze the Cauco project options",
            "use_reasoning": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reasoning_requested"] is True
    assert payload["reasoning_invoked"] is True
    assert payload["provider"] == "noop"
    assert payload["proposal_produced"] is False
    assert payload["planning"]["execution_performed"] is False


def test_reasoning_planning_response_is_proposal_only(
    reasoning_client: TestClient,
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={"instruction": "Plan the next Cauco project task"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["planning"]["proposal_only"] is True
    assert payload["planning"]["execution_performed"] is False
    assert payload["planning"]["review_approved"] is False
    assert payload["planning"]["runtime_started"] is False
    for forbidden in (
        "execution_id",
        "mutation_id",
        "review_id",
        "runtime_state",
        "tool_execution_result",
    ):
        assert forbidden not in response.text


def test_provider_failure_falls_back_without_leaking_secrets(
    reasoning_client: TestClient,
) -> None:
    class FailingEngine:
        def reason(self, request: ReasoningRequest) -> ReasoningResult:
            raise RuntimeError("secret-provider-credential")

    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = (
        ReasoningService(FailingEngine())
    )

    response = reasoning_client.post(
        "/api/reasoning/plan",
        json={"instruction": "Analyze the Cauco project options", "use_reasoning": True},
    )

    assert response.status_code == 200
    assert response.json()["reasoning_invoked"] is True
    assert response.json()["planning"]["status"] == "planned"
    assert "secret-provider-credential" not in response.text


def test_reasoning_route_and_service_are_bootstrapped(reasoning_client: TestClient) -> None:
    paths = reasoning_client.get("/openapi.json").json()["paths"]

    assert "/api/reasoning/plan" in paths
    assert reasoning_client.app.state.reasoning_aware_planning_service is not None


def test_conversation_uses_deterministic_plan_without_reasoning(
    reasoning_client: TestClient,
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "Plan the next Cauco project task", "use_reasoning": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_status"] == "planned"
    assert payload["reasoning_invoked"] is False
    assert payload["plan"]["objective"] in payload["message"]
    assert payload["proposal_only"] is True
    assert payload["execution_performed"] is False
    assert payload["review_approved"] is False
    assert payload["runtime_started"] is False


@pytest.mark.parametrize(
    "instruction",
    [
        "What you can do",
        "WHAT DO YOU DO!",
        "What can Cauco do?",
        "How can you help me?",
        "  what can you help me with...  ",
    ],
)
def test_conversation_meta_variants_use_deterministic_fallback_without_provider(
    reasoning_client: TestClient,
    instruction: str,
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": instruction, "use_reasoning": False},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "advisory" in payload["message"]
    assert payload["planning_status"] == "no_match"
    assert payload["reasoning_invoked"] is False
    assert payload["proposal_only"] is True
    assert payload["execution_performed"] is False
    assert payload["review_approved"] is False
    assert payload["runtime_started"] is False


@pytest.mark.parametrize(
    "instruction",
    ["¿Qué puedes hacer?", "¿Qué sabes hacer?", "¿Cuáles son tus capacidades?", "Dime qué puedes hacer", "What can you do?", "What are your capabilities?"],
)
def test_conversation_capability_inquiry_uses_summary_without_reasoning_or_ai(
    reasoning_client: TestClient, instruction: str
) -> None:
    class FailingEngine:
        def reason(self, request: ReasoningRequest) -> ReasoningResult:
            raise AssertionError("Reasoning must not run for capability inquiry")

    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = ReasoningService(FailingEngine())
    ai_service = RecordingAIService(response="must not be used")
    reasoning_client.app.state.ai_service = ai_service

    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": instruction, "use_reasoning": True},
    )
    assert response.status_code == 200
    assert response.json()["planning_status"] == "capability_summary"
    assert response.json()["reasoning_invoked"] is False
    assert ai_service.calls == 0


@pytest.mark.parametrize(
    "instruction",
    ["Check what I can do on my calendar tomorrow", "What can you do with my calendar tomorrow?"],
)
def test_operational_requests_do_not_use_meta_fallback(
    reasoning_client: TestClient, instruction: str
) -> None:
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": instruction, "use_reasoning": False},
    )
    assert response.status_code == 200
    assert response.json()["planning_status"] == "planned"
    assert response.json()["message"] != "Cauco can help plan and explain tasks in an advisory way. It does not execute actions or change your system from this conversation."


def test_conversation_capability_inquiry_does_not_use_advisory_reasoning(
    reasoning_client: TestClient,
) -> None:
    engine = RecordingEngine(
        ReasoningResult(
            provider="test", model="test-model", text="I can explain Cauco's capabilities.", reasoning_performed=True
        )
    )
    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = ReasoningService(engine)
    ai_service = RecordingAIService(response="AI fallback should not run")
    reasoning_client.app.state.ai_service = ai_service
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "What can you do?", "use_reasoning": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_status"] == "capability_summary"
    assert payload["reasoning_invoked"] is False
    assert payload["plan"] is None
    assert payload["execution_performed"] is False
    assert payload["review_approved"] is False
    assert payload["runtime_started"] is False
    assert engine.calls == 0
    assert ai_service.calls == 0


def test_conversation_noop_uses_existing_ai_service_fallback(
    reasoning_client: TestClient,
) -> None:
    ai_service = RecordingAIService(response="Local AI advisory response.")
    reasoning_client.app.state.ai_service = ai_service

    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "Tell me a short joke", "use_reasoning": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Local AI advisory response."
    assert payload["planning_status"] == "no_match"
    assert payload["plan"] is None
    assert payload["reasoning_invoked"] is True
    assert payload["execution_performed"] is False
    assert ai_service.calls == 1


def test_conversation_empty_reasoning_and_unavailable_ai_returns_503(
    reasoning_client: TestClient,
) -> None:
    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = ReasoningService(
        RecordingEngine(ReasoningResult(provider="test", model="m", text="", reasoning_performed=True))
    )
    ai_service = RecordingAIService(error=ProviderUnavailableError("offline"))
    reasoning_client.app.state.ai_service = ai_service

    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "Tell me a short joke", "use_reasoning": True},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Advisory conversation is unavailable; no action was taken."
    assert ai_service.calls == 1


def test_capability_inquiry_does_not_depend_on_reasoning_or_ai_availability(
    reasoning_client: TestClient,
) -> None:
    class FailingEngine:
        def reason(self, request: ReasoningRequest) -> ReasoningResult:
            raise RuntimeError("provider secret")

    reasoning_client.app.state.reasoning_orchestration_service.reasoning_service = ReasoningService(FailingEngine())
    reasoning_client.app.state.ai_service = RecordingAIService(
        error=ProviderUnavailableError("offline")
    )
    response = reasoning_client.post(
        "/api/reasoning/conversation/respond",
        json={"instruction": "What can you do?", "use_reasoning": True},
    )
    assert response.status_code == 200
    assert response.json()["planning_status"] == "capability_summary"
    assert "provider secret" not in response.text


def draft_request(client, instruction, conversation_id=CONVERSATION_ID):
    response = client.post("/api/reasoning/conversation/respond", json={
        "instruction": instruction, "conversation_id": conversation_id,
    })
    assert response.status_code == 200, response.text
    return response.json()


def create_draft(client):
    return draft_request(client, "Crea un archivo prueba.txt con este contenido: hola")


def test_conversation_creates_persistent_draft_without_review_or_target(reasoning_client, monkeypatch):
    import hashlib
    from uuid import UUID

    def forbidden(*args, **kwargs):
        pytest.fail("Creating a draft must not create a review or invoke mutation")

    state = reasoning_client.app.state
    monkeypatch.setattr(state.agent_plan_review_service, "create", forbidden)
    monkeypatch.setattr(state.tool_adapter_registry.get("filesystem", "write_text_file"), "execute", forbidden)
    data = create_draft(reasoning_client)
    assert data["planning_status"] == "draft_active"
    assert data["draft_status"] == "active"
    assert data["draft_target"] == "prueba.txt"
    assert data["draft_content"] == "hola"
    assert data["draft_digest"] == hashlib.sha256(b"hola").hexdigest()
    assert data["review_id"] is None and data["plan"] is None
    assert data["execution_performed"] is False
    assert "conversation_id" not in data
    assert not (state.workspace_policy.root / "prueba.txt").exists()
    draft = state.filesystem_draft_store.get_active_by_conversation(UUID(CONVERSATION_ID))
    assert draft.draft_id == data["draft_id"]
    assert draft.digest == data["draft_digest"]
    assert (state.filesystem_draft_store.root / f"{draft.draft_id}.json").is_file()


def test_conversation_recovers_active_draft_and_isolates_conversations(reasoning_client):
    from cauco_core.filesystem_drafts import FilesystemDraftStore

    original = create_draft(reasoning_client)
    state = reasoning_client.app.state
    state.filesystem_draft_store = FilesystemDraftStore(state.workspace_policy.root)
    recovered = draft_request(reasoning_client, "Muéstrame el borrador")
    for key in ("draft_id", "draft_status", "draft_target", "draft_content", "draft_digest"):
        assert recovered[key] == original[key]
    state.ai_service = RecordingAIService(response="Sin borrador")
    other = draft_request(reasoning_client, "Muéstrame el borrador", CONVERSATION_ID_TWO)
    assert other["draft_id"] is None
    assert other["planning_status"] not in {"draft_active", "draft_finalized"}


@pytest.mark.parametrize("instruction", [
    "Cambia el contenido a: adiós",
    "Actualiza el contenido del borrador: adiós",
    "Escribe un archivo prueba.txt con este contenido: adiós",
])
def test_conversation_updates_same_draft(reasoning_client, instruction):
    import hashlib

    original = create_draft(reasoning_client)
    updated = draft_request(reasoning_client, instruction)
    assert updated["draft_id"] == original["draft_id"]
    assert updated["draft_content"] == "adiós"
    assert updated["draft_digest"] == hashlib.sha256("adiós".encode()).hexdigest()
    assert updated["draft_digest"] != original["draft_digest"]
    assert len(list(reasoning_client.app.state.filesystem_draft_store.root.glob("fsdraft_*.json"))) == 1
    assert not (reasoning_client.app.state.workspace_policy.root / "prueba.txt").exists()


@pytest.mark.parametrize("acceptance", ["está bien", "déjalo así", "guárdalo"])
def test_conversation_finalizes_once_after_verification(reasoning_client, monkeypatch, acceptance):
    from uuid import UUID

    original = create_draft(reasoning_client)
    state = reasoning_client.app.state
    adapter = state.tool_adapter_registry.get("filesystem", "write_text_file")
    execute = adapter.execute
    calls = []

    def recording(request):
        calls.append(request)
        assert state.filesystem_draft_store.get(original["draft_id"]).status == "active"
        return execute(request)

    monkeypatch.setattr(adapter, "execute", recording)
    finalized = draft_request(reasoning_client, acceptance)
    assert finalized["draft_id"] == original["draft_id"]
    assert finalized["draft_status"] == "finalized"
    assert finalized["planning_status"] == "draft_finalized"
    assert finalized["execution_performed"] is True
    assert finalized["draft_digest"] == original["draft_digest"]
    assert (state.workspace_policy.root / "prueba.txt").read_text() == "hola"
    assert state.filesystem_draft_store.get(original["draft_id"]).status == "finalized"
    assert state.filesystem_draft_store.get_active_by_conversation(UUID(CONVERSATION_ID)) is None
    state.ai_service = RecordingAIService(response="No hay borrador activo")
    second = draft_request(reasoning_client, acceptance)
    assert second["draft_id"] is None
    assert second["execution_performed"] is False
    assert len(calls) == 1
    assert calls[0].arguments["overwrite_policy"] == "create_only"


@pytest.mark.parametrize("race", [False, True])
def test_conversation_collision_keeps_draft_active(reasoning_client, monkeypatch, race):
    original = create_draft(reasoning_client)
    state = reasoning_client.app.state
    target = state.workspace_policy.root / "prueba.txt"
    if race:
        adapter = state.tool_adapter_registry.get("filesystem", "write_text_file")
        execute = adapter.execute

        def collide(request):
            target.write_text("external")
            return execute(request)

        monkeypatch.setattr(adapter, "execute", collide)
    else:
        target.write_text("external")
    data = draft_request(reasoning_client, "guárdalo")
    assert data["planning_status"] == "draft_conflict"
    assert data["draft_status"] == "active"
    assert data["draft_id"] == original["draft_id"]
    assert target.read_text() == "external"
    assert state.filesystem_draft_store.get(original["draft_id"]).status == "active"


def test_conversation_bad_result_digest_does_not_finalize(reasoning_client, monkeypatch):
    from dataclasses import replace

    original = create_draft(reasoning_client)
    state = reasoning_client.app.state
    adapter = state.tool_adapter_registry.get("filesystem", "write_text_file")
    execute = adapter.execute

    def wrong_digest(request):
        result = execute(request)
        return replace(result, structured_data={**result.structured_data, "after_digest": "incorrect"})

    monkeypatch.setattr(adapter, "execute", wrong_digest)
    data = draft_request(reasoning_client, "guárdalo")
    assert data["planning_status"] == "draft_verification_failed"
    assert state.filesystem_draft_store.get(original["draft_id"]).status == "active"


@pytest.mark.parametrize("target", ["cauco-drafts/internal.json", "secrets/file.txt", "package.json", "missing/file.txt"])
def test_conversation_draft_rejects_forbidden_targets(reasoning_client, target):
    response = reasoning_client.post("/api/reasoning/conversation/respond", json={
        "instruction": f"Crea un archivo {target} con este contenido: hola",
    })
    assert response.status_code == 403
    assert not list(reasoning_client.app.state.filesystem_draft_store.root.glob("fsdraft_*.json"))


def test_conversation_draft_storage_is_not_exposed(reasoning_client):
    original = create_draft(reasoning_client)
    response = reasoning_client.post("/api/reasoning/conversation/respond", json={
        "instruction": f"Lee el archivo cauco-drafts/{original['draft_id']}.json",
        "conversation_id": CONVERSATION_ID_TWO,
    })
    assert response.status_code == 403
    listing = draft_request(reasoning_client, "Lista los archivos del workspace", CONVERSATION_ID_TWO)
    assert "cauco-drafts" not in listing["message"]


def test_conversation_finalize_revalidates_symlinks(reasoning_client, tmp_path):
    original = create_draft(reasoning_client)
    state = reasoning_client.app.state
    outside = tmp_path / "outside.txt"
    outside.write_text("external")
    (state.workspace_policy.root / "prueba.txt").symlink_to(outside)
    data = draft_request(reasoning_client, "guárdalo")
    assert data["planning_status"] == "draft_conflict"
    assert state.filesystem_draft_store.get(original["draft_id"]).status == "active"
    assert outside.read_text() == "external"


def test_conversation_existing_target_replacement_requires_preview_confirmation(reasoning_client):
    client = reasoning_client
    target = client.app.state.workspace_policy.root / "prueba.txt"
    target.write_text("original")
    data = draft_request(client, "Reemplaza archivo prueba.txt con este contenido: nuevo")
    assert data["planning_status"] == "pending_review"
    assert data["draft_id"] is None
    assert target.read_text() == "original"
    approved = client.post(f"/api/agents/plan-reviews/{data['review_id']}/approve", json={})
    assert approved.status_code == 200, approved.text
    execution_response = client.post("/api/executions", json={"review_id": data["review_id"]})
    assert execution_response.status_code == 201, execution_response.text
    execution = execution_response.json()
    step = next(item for item in execution["step_records"] if item["operation_id"] == "write_text_file")
    url = f"/api/executions/{execution['execution_id']}/steps/{step['step_index']}"
    preview_response = client.post(url + "/mutation-preview", json={})
    assert preview_response.status_code == 201, preview_response.text
    preview = preview_response.json()
    assert target.read_text() == "original"
    confirmed = client.post(url + "/confirm-mutation", json={
        "preview_id": preview["preview_id"], "preview_digest": preview["preview_digest"],
        "confirmation_phrase": preview["confirmation_phrase"],
    })
    assert confirmed.status_code == 200, confirmed.text
    assert target.read_text() == "nuevo"
    result = next(item for item in confirmed.json()["step_records"] if item["operation_id"] == "write_text_file")
    assert result["result"]["structured_data"]["replaced"] is True
    assert result["result"]["structured_data"]["verification_passed"] is True


@pytest.mark.parametrize("instruction", [
    "Cauco, crea un archivo prueba punto txt con este contenido hola punto md!",
    "Cojo crea un archivo prueba punto txt con este contenido: hola punto md!",
])
def test_conversation_dictated_write_preserves_content(reasoning_client, instruction):
    data = draft_request(reasoning_client, instruction)
    assert data["planning_status"] == "draft_active"
    assert data["draft_target"] == "prueba.txt"
    assert data["draft_content"] == "hola punto md!"
    assert data["execution_performed"] is False
    assert not (reasoning_client.app.state.workspace_policy.root / "prueba.txt").exists()
