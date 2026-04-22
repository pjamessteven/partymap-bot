"""Main FastAPI application with dashboard."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.agents import router as agents_router
from src.api.errors import router as errors_router
from src.api.goabase import router as goabase_router
from src.api.jobs import router as jobs_router
from src.api.pipelines import router as pipelines_router
from src.api.refresh import router as refresh_router
from src.config import get_settings
from src.core.database import engine
from src.dashboard.router import router as dashboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Configure structured logging
    from src.utils.logging import configure_logging
    configure_logging()

    # Startup: verify database connectivity (migrations run via entrypoint.sh)
    from sqlalchemy import text
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    yield
    # Shutdown


def create_app() -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="PartyMap Festival Bot",
        description="Automated festival discovery and research bot",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(dashboard_router, prefix="/api")
    app.include_router(agents_router, prefix="/api")  # LangGraph-compatible API
    app.include_router(jobs_router, prefix="/api")
    app.include_router(refresh_router, prefix="/api")
    app.include_router(goabase_router, prefix="/api")
    app.include_router(pipelines_router, prefix="/api")
    app.include_router(errors_router, prefix="/api")

    # Static files
    app.mount("/static", StaticFiles(directory="src/dashboard/static"), name="static")

    @app.get("/")
    async def root():
        """Redirect to dashboard."""
        return {"message": "PartyMap Festival Bot", "dashboard": "/static/index.html"}

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
