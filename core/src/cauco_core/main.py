import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cauco_core.api.routes import router
from cauco_core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Cauco Core", version="0.1.0")
    app.state.settings = settings or Settings()

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
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )
    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    settings = Settings()
    uvicorn.run("cauco_core.main:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    run()
