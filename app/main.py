from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.database import async_session_factory
from app.logger import setup_logging
from app.models.project import Project
from app.routers import business, ingest, knowledge, projects, prompts, test_ui

setup_logging()

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: check readiness before serving."""

    from app.models.graph import GraphNode
    from app.models.knowledge import KnowledgeDocument

    async with async_session_factory() as session:
        result = await session.execute(
            select(Project).order_by(Project.created_at.desc()).limit(1)
        )
        project = result.scalar_one_or_none()
        project_name = project.name if project else "Unknown"

        doc_count_res = await session.execute(select(func.count(KnowledgeDocument.id)))
        docs_count = doc_count_res.scalar_one()

        node_count_res = await session.execute(select(func.count(GraphNode.id)))
        nodes_count = node_count_res.scalar_one()

        logger.info(
            "startup_handshake",
            message=f"Project: {project_name} | Docs: {docs_count} "
            f"| Graph Nodes: {nodes_count}",
        )

    yield


app = FastAPI(
    title="Prumo API",
    description="Context orchestration engine for agentic IDEs",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(projects.router)
app.include_router(business.router)
app.include_router(ingest.router)
app.include_router(knowledge.router)
app.include_router(prompts.router)
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
