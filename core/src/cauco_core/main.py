from contextlib import suppress
from datetime import timedelta

import uvicorn
from cauco_agents import AgentRouter, create_default_registry
from cauco_tools import ToolAdapterRegistry
from cauco_tools import create_default_registry as create_default_tool_registry
from cauco_tools.adapters import (
    FilesystemAdapter,
    FilesystemTextMutationAdapter,
    GitAddAdapter,
    GitCommitAdapter,
    GitPushAdapter,
    GitStatusAdapter,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cauco_core.agents.context import AgentContextResolver
from cauco_core.agents.planning import AgentPlanningService
from cauco_core.agents.review_service import AgentPlanReviewService
from cauco_core.agents.sqlite_store import SQLiteAgentPlanReviewStore
from cauco_core.ai.base import AIProvider
from cauco_core.ai.ollama import OllamaProvider
from cauco_core.ai.service import AIService
from cauco_core.api.agent_routes import router as agent_router_api
from cauco_core.api.ai_routes import router as ai_router
from cauco_core.api.context_routes import router as context_router
from cauco_core.api.execution_routes import router as execution_router
from cauco_core.api.executive_routes import router as executive_router
from cauco_core.api.experience_routes import router as experience_router
from cauco_core.api.learning_guidance_routes import router as learning_guidance_router
from cauco_core.api.memory_candidate_routes import router as memory_candidate_router
from cauco_core.api.memory_routes import router as memory_router
from cauco_core.api.mutation_routes import router as mutation_router
from cauco_core.api.perception_routes import router as perception_router
from cauco_core.api.routes import router
from cauco_core.api.tool_routes import router as tool_router
from cauco_core.api.verification_routes import router as verification_router
from cauco_core.config import Settings
from cauco_core.context.builder import ContextBuilder
from cauco_core.execution.policy import WorkspacePolicy
from cauco_core.execution.service import ExecutionService
from cauco_core.execution.sqlite_store import SQLiteExecutionStore
from cauco_core.executive import ExecutiveControlService, ExecutiveStateResolver
from cauco_core.learning.service import ExperienceConsolidationService
from cauco_core.learning.sqlite_store import SQLiteExperienceStore
from cauco_core.learning_guidance.resolver import LearningGuidanceResolver
from cauco_core.memory.context import MemoryContextBuilder
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.exceptions import MemoryDirectoryError
from cauco_core.memory.search import MemorySearch
from cauco_core.memory.service import MemoryService
from cauco_core.memory_candidates.promotion import MemoryCandidatePromotionService
from cauco_core.memory_candidates.service import MemoryCandidateService
from cauco_core.memory_candidates.sqlite_store import SQLiteMemoryCandidateStore
from cauco_core.memory_writing.applier import MemoryWriteProposalApplier
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.sqlite_store import SQLiteMemoryWriteProposalStore
from cauco_core.mutations.memory_adapter import CoreMemoryMutationAdapter
from cauco_core.mutations.service import MutationService
from cauco_core.mutations.sqlite_store import SQLiteMutationPreviewStore
from cauco_core.perception import (
    BrainMemoryPerceptionSource,
    OperationalStatePerceptionSource,
    PerceptionManager,
    PerceptionSourceRegistry,
)
from cauco_core.persistence import SQLiteDatabase
from cauco_core.verification import VerificationService
from cauco_core.verification.sqlite_store import SQLiteVerificationStore


def build_ai_provider(settings: Settings) -> AIProvider:
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        default_model=settings.default_model,
        timeout=settings.ai_request_timeout,
        temperature=settings.ai_temperature,
        max_output_tokens=settings.ai_max_output_tokens,
    )


def create_app(settings: Settings | None = None, ai_provider: AIProvider | None = None) -> FastAPI:
    app = FastAPI(title="Cauco Core", version="0.1.0")
    app.state.settings = settings or Settings()
    app.state.agent_registry = create_default_registry()
    app.state.tool_registry = create_default_tool_registry()
    app.state.tool_adapter_registry = ToolAdapterRegistry()
    app.state.workspace_policy = None
    workspace = app.state.settings.resolved_workspace_dir()
    if workspace is not None:
        app.state.workspace_policy = WorkspacePolicy(workspace)
        app.state.tool_adapter_registry.register(
            FilesystemAdapter(
                app.state.workspace_policy.root,
                max_file_bytes=app.state.settings.execution_max_file_bytes,
            )
        )
        app.state.tool_adapter_registry.register(GitStatusAdapter(app.state.workspace_policy.root))
        app.state.tool_adapter_registry.register(
            GitAddAdapter(
                app.state.workspace_policy.root,
                max_file_bytes=app.state.settings.execution_max_file_bytes,
            )
        )
        app.state.tool_adapter_registry.register(
            GitCommitAdapter(
                app.state.workspace_policy.root,
                max_file_bytes=app.state.settings.execution_max_file_bytes,
            )
        )
        app.state.tool_adapter_registry.register(
            GitPushAdapter(
                app.state.workspace_policy.root,
                max_file_bytes=app.state.settings.execution_max_file_bytes,
            )
        )
        app.state.tool_adapter_registry.register(
            FilesystemTextMutationAdapter(
                app.state.workspace_policy.root,
                max_content_chars=app.state.settings.mutation_max_content_characters,
            )
        )
    app.state.agent_router = AgentRouter(app.state.agent_registry)
    app.state.memory_service = MemoryService(
        app.state.settings.resolved_brain_dir(), app.state.settings.memory_max_file_size
    )
    app.state.memory_search = MemorySearch(app.state.memory_service)
    app.state.memory_engine = MemoryEngine(app.state.memory_service)
    # Preserve startup behavior for an invalid configured path; memory refresh
    # still exposes the domain error after startup.
    with suppress(MemoryDirectoryError):
        app.state.memory_engine.refresh()
    app.state.perception_source_registry = PerceptionSourceRegistry()
    app.state.brain_memory_perception_source = BrainMemoryPerceptionSource(
        app.state.memory_engine,
        app.state.memory_search,
    )
    app.state.perception_source_registry.register(app.state.brain_memory_perception_source)
    app.state.perception_manager = PerceptionManager(app.state.perception_source_registry)
    app.state.agent_context_resolver = AgentContextResolver(app.state.memory_engine)
    app.state.agent_planning_service = AgentPlanningService(
        app.state.agent_router,
        app.state.agent_registry,
        app.state.agent_context_resolver,
    )
    app.state.database = SQLiteDatabase(
        app.state.settings.resolved_database_path(),
        busy_timeout_ms=app.state.settings.database_busy_timeout_ms,
    )
    app.state.agent_plan_review_store = SQLiteAgentPlanReviewStore(
        app.state.database,
        default_ttl_seconds=app.state.settings.agent_plan_review_ttl_seconds,
        max_records=app.state.settings.agent_plan_review_max_records,
    )
    app.state.agent_plan_review_service = AgentPlanReviewService(
        app.state.agent_planning_service,
        app.state.agent_plan_review_store,
    )
    app.state.context_builder = ContextBuilder(app.state.memory_engine)
    app.state.memory_write_proposal_store = SQLiteMemoryWriteProposalStore(
        app.state.database,
        ttl=timedelta(seconds=app.state.settings.memory_write_proposal_ttl_seconds),
    )
    app.state.memory_write_proposal_builder = MemoryWriteProposalBuilder(app.state.memory_engine)
    app.state.memory_write_proposal_applier = MemoryWriteProposalApplier(
        app.state.memory_engine,
        app.state.memory_write_proposal_store,
    )
    app.state.tool_adapter_registry.register(
        CoreMemoryMutationAdapter(
            app.state.memory_write_proposal_builder,
            app.state.memory_write_proposal_store,
            app.state.memory_write_proposal_applier,
        )
    )
    app.state.execution_store = SQLiteExecutionStore(
        app.state.database,
        max_records=app.state.settings.execution_max_records,
    )
    app.state.operational_state_perception_source = OperationalStatePerceptionSource(
        app.state.agent_plan_review_store,
        app.state.execution_store,
    )
    app.state.perception_source_registry.register(app.state.operational_state_perception_source)
    app.state.verification_store = SQLiteVerificationStore(
        app.state.database,
        max_records=app.state.settings.verification_max_records,
    )
    app.state.verification_service = VerificationService(
        review_store=app.state.agent_plan_review_store,
        execution_store=app.state.execution_store,
        verification_store=app.state.verification_store,
    )
    app.state.experience_store = SQLiteExperienceStore(
        app.state.database, max_records=app.state.settings.experience_max_records
    )
    app.state.experience_consolidation_service = ExperienceConsolidationService(
        verification_store=app.state.verification_store,
        experience_store=app.state.experience_store,
    )
    app.state.memory_candidate_store = SQLiteMemoryCandidateStore(
        app.state.database,
        ttl=timedelta(seconds=app.state.settings.memory_candidate_ttl_seconds),
        max_records=app.state.settings.memory_candidate_max_records,
    )
    app.state.memory_candidate_service = MemoryCandidateService(
        experience_store=app.state.experience_store,
        candidate_store=app.state.memory_candidate_store,
    )
    app.state.memory_candidate_promotion_service = MemoryCandidatePromotionService(
        app.state.memory_candidate_store,
        app.state.memory_write_proposal_builder,
        app.state.memory_write_proposal_store,
    )
    app.state.learning_guidance_resolver = LearningGuidanceResolver(
        app.state.memory_candidate_store,
        app.state.memory_write_proposal_store,
    )
    app.state.agent_context_resolver.learning_guidance_resolver = (
        app.state.learning_guidance_resolver
    )
    app.state.executive_control_service = ExecutiveControlService()
    app.state.executive_state_resolver = ExecutiveStateResolver(
        app.state.agent_plan_review_store,
        app.state.execution_store,
        app.state.verification_store,
    )
    app.state.execution_service = ExecutionService(
        app.state.agent_plan_review_store,
        app.state.tool_registry,
        app.state.tool_adapter_registry,
        app.state.execution_store,
        app.state.workspace_policy,
    )
    app.state.mutation_preview_store = SQLiteMutationPreviewStore(
        app.state.database,
        ttl_seconds=app.state.settings.mutation_preview_ttl_seconds,
        max_records=app.state.settings.mutation_preview_max_records,
    )
    app.state.mutation_service = MutationService(
        app.state.execution_service,
        app.state.execution_store,
        app.state.agent_plan_review_store,
        app.state.tool_registry,
        app.state.tool_adapter_registry,
        app.state.mutation_preview_store,
        app.state.memory_write_proposal_builder,
        app.state.memory_write_proposal_store,
    )
    app.state.memory_context_builder = MemoryContextBuilder(
        app.state.memory_service,
        app.state.memory_search,
        max_files=app.state.settings.memory_context_max_files,
        max_total_characters=app.state.settings.memory_context_max_characters,
    )
    app.state.ai_service = AIService(
        ai_provider or build_ai_provider(app.state.settings),
        memory_context_builder=app.state.memory_context_builder,
        context_builder=app.state.context_builder,
        memory_engine=app.state.memory_engine,
        max_context_characters=app.state.settings.memory_context_max_characters,
    )

    # Obsidian's desktop shell may use an app:// or localhost origin. These explicit
    # local origins support development without opening the API to arbitrary websites.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "app://obsidian.md",
            "http://localhost",
            "http://127.0.0.1",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )
    app.include_router(router)
    app.include_router(agent_router_api)
    app.include_router(tool_router)
    app.include_router(execution_router)
    app.include_router(executive_router)
    app.include_router(verification_router)
    app.include_router(experience_router)
    app.include_router(memory_candidate_router)
    app.include_router(mutation_router)
    app.include_router(context_router)
    app.include_router(memory_router)
    app.include_router(learning_guidance_router)
    app.include_router(perception_router)
    app.include_router(ai_router)
    return app


app = create_app()


def run() -> None:
    settings = Settings()
    uvicorn.run("cauco_core.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
