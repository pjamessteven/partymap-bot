"""Main FastAPI application with dashboard."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.agents import router as agents_router
from src.api.costs import router as costs_router
from src.api.discovery import router as discovery_router
from src.api.errors import router as errors_router
from src.api.festivals import router as festivals_router
from src.api.goabase import router as goabase_router
from src.api.jobs import router as jobs_router
from src.api.queries import router as queries_router
from src.api.refresh import router as refresh_router
from src.api.settings import router as settings_router
from src.api.stats import router as stats_router
from src.config import get_settings
from src.core.database import engine


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
    # Dispose database engine
    await engine.dispose()

    # Close Postgres checkpointer connection
    from src.core.database import close_postgres_checkpointer
    await close_postgres_checkpointer()

    # Cancel any running background tasks
    from src.api.agents import _running_tasks
    if _running_tasks:
        for task in list(_running_tasks):
            if not task.done():
                task.cancel()
        # Give tasks a moment to clean up
        await asyncio.sleep(0.5)


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
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if not origins:
        origins = ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(festivals_router, prefix="/api")  # Main festival CRUD
    app.include_router(agents_router, prefix="/api")  # LangGraph-compatible API
    app.include_router(jobs_router, prefix="/api")
    app.include_router(refresh_router, prefix="/api")
    app.include_router(goabase_router, prefix="/api")
    app.include_router(errors_router, prefix="/api")
    app.include_router(stats_router, prefix="/api")
    app.include_router(discovery_router, prefix="/api")
    app.include_router(queries_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(costs_router, prefix="/api")

    @app.get("/")
    async def root():
        """API root."""
        return {
            "message": "PartyMap Festival Bot API",
            "docs": "/docs",
            "version": "0.1.0"
        }

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
