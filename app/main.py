# Copyright (C) 2026 Dione Bastos
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


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
from app.models.knowledge import KnowledgeDocument
from app.models.project import Project
from app.routers import chat, cookbooks, knowledge, projects, test_ui

setup_logging()

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: check readiness before serving."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project).order_by(Project.created_at.desc()).limit(1)
        )
        project = result.scalar_one_or_none()
        project_name = project.name if project else "Unknown"

        doc_count_res = await session.execute(select(func.count(KnowledgeDocument.id)))
        docs_count = doc_count_res.scalar_one()

        logger.info(
            "startup_handshake",
            message=f"Project: {project_name} | Docs: {docs_count}",
        )

    yield


app = FastAPI(
    title="Prumo Lite API",
    description=(
        "Gerador Inteligente de Cookbooks para o ecossistema Stellar "
        "baseado puramente em modelos Gemini."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(projects.router)
app.include_router(knowledge.router)
app.include_router(chat.router)
app.include_router(cookbooks.router)
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
    return {"status": "ok", "version": "0.2.0"}
