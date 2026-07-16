import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cauco_core.ai.base import AIProvider
from cauco_core.ai.ollama import OllamaProvider
from cauco_core.ai.service import AIService
from cauco_core.api.ai_routes import router as ai_router
from cauco_core.api.routes import router
from cauco_core.config import Settings


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
    app.state.ai_service = AIService(ai_provider or build_ai_provider(app.state.settings))

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
    app.include_router(ai_router)
    return app


app = create_app()


def run() -> None:
    settings = Settings()
    uvicorn.run("cauco_core.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
