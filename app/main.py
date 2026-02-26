from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError
from app.database import async_session_factory
from app.logger import setup_logging
from app.models.project import Project
from app.routers import ingest, knowledge, projects, test_ui

setup_logging()

logger = structlog.get_logger()

DEFAULT_PROJECT_NAME = "Trustless Escrow Project"
DEFAULT_PROJECT_DESCRIPTION = "Auto-generated default project."


async def _bootstrap_default_project() -> None:
    """Ensure at least one project exists in the database.

    This runs once at startup, outside any request cycle.
    Uses its own session to maintain lifecycle isolation.
    A UNIQUE constraint on project.name guards against race conditions
    in multi-worker deployments.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(func.count(Project.id)))
        project_count = result.scalar_one()

        if project_count > 0:
            logger.info("bootstrap_skipped", existing_projects=project_count)
            return

        default_project = Project(
            name=DEFAULT_PROJECT_NAME,
            description=DEFAULT_PROJECT_DESCRIPTION,
        )
        session.add(default_project)

        try:
            await session.commit()
            logger.info(
                "bootstrap_default_project_created",
                project_name=DEFAULT_PROJECT_NAME,
                project_id=str(default_project.id),
            )
        except IntegrityError:
            # Another worker already created the project — safe to ignore.
            await session.rollback()
            logger.info(
                "bootstrap_duplicate_suppressed",
                project_name=DEFAULT_PROJECT_NAME,
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: bootstrap default project before serving."""
    await _bootstrap_default_project()
    yield


app = FastAPI(
    title="Prumo API",
    description="Context orchestration engine for agentic IDEs",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(projects.router)
app.include_router(ingest.router)
app.include_router(knowledge.router)
app.include_router(test_ui.router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Global exception handler for application domain errors."""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Return application health status."""
    return {"status": "ok", "version": "0.1.0"}
