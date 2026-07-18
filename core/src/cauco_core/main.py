from contextlib import suppress
from datetime import timedelta

import uvicorn
from cauco_agents import AgentRouter, create_default_registry
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cauco_core.agents.context import AgentContextResolver
from cauco_core.agents.planning import AgentPlanningService
from cauco_core.ai.base import AIProvider
from cauco_core.ai.ollama import OllamaProvider
from cauco_core.ai.service import AIService
from cauco_core.api.agent_routes import router as agent_router_api
from cauco_core.api.ai_routes import router as ai_router
from cauco_core.api.context_routes import router as context_router
from cauco_core.api.memory_routes import router as memory_router
from cauco_core.api.routes import router
from cauco_core.config import Settings
from cauco_core.context.builder import ContextBuilder
from cauco_core.memory.context import MemoryContextBuilder
from cauco_core.memory.engine import MemoryEngine
from cauco_core.memory.exceptions import MemoryDirectoryError
from cauco_core.memory.search import MemorySearch
from cauco_core.memory.service import MemoryService
from cauco_core.memory_writing.applier import MemoryWriteProposalApplier
from cauco_core.memory_writing.proposal_builder import MemoryWriteProposalBuilder
from cauco_core.memory_writing.store import MemoryWriteProposalStore


def build_ai_provider(settings: Settings) -> AIProvider:
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        default_model=settings.default_model,
        timeout=settings.ai_request_timeout,
        temperature=settings.ai_temperature,
        max_output_tokens=settings.ai_max_output_tokens,
    )


def create_app(
    settings: Settings | None = None, ai_provider: AIProvider | None = None
) -> FastAPI:
    app = FastAPI(title="Cauco Core", version="0.1.0")
    app.state.settings = settings or Settings()
    app.state.agent_registry = create_default_registry()
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
    app.state.agent_context_resolver = AgentContextResolver(app.state.memory_engine)
    app.state.agent_planning_service = AgentPlanningService(
        app.state.agent_router,
        app.state.agent_registry,
        app.state.agent_context_resolver,
    )
    app.state.context_builder = ContextBuilder(app.state.memory_engine)
    app.state.memory_write_proposal_store = MemoryWriteProposalStore(
        ttl=timedelta(seconds=app.state.settings.memory_write_proposal_ttl_seconds)
    )
    app.state.memory_write_proposal_builder = MemoryWriteProposalBuilder(
        app.state.memory_engine
    )
    app.state.memory_write_proposal_applier = MemoryWriteProposalApplier(
        app.state.memory_engine,
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
    app.include_router(context_router)
    app.include_router(memory_router)
    app.include_router(ai_router)
    return app


app = create_app()


def run() -> None:
    settings = Settings()
    uvicorn.run("cauco_core.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
