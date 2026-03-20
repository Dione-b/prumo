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


# TECH_DEBT_003: WARNING - No CSRF protection. Bind to 127.0.0.1 only.

from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.knowledge import KnowledgeDocument
from app.models.project import Project
from app.services.knowledge_gemini import process_document_task
from app.services.knowledge_orchestrator import query_rag

logger = structlog.get_logger()

router = APIRouter(prefix="/ui", tags=["UI Testbed"])
templates = Jinja2Templates(directory="templates")

MAX_TEXT_MATERIALIZATION_BYTES = 10 * 1024 * 1024  # 10MB


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render the HTMX test dashboard."""
    result = await db.execute(select(Project).order_by(Project.created_at))
    projects = result.scalars().all()

    doc_count_result = await db.execute(select(func.count(KnowledgeDocument.id)))
    doc_count = doc_count_result.scalar_one()

    docs_result = await db.execute(
        select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    )
    recent_docs = docs_result.scalars().all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "projects": projects,
            "doc_count": doc_count,
            "node_count": 0,  # Mantido por compatibilidade de template
            "recent_docs": recent_docs,
        },
    )


def _stream_to_tempfile(upload_stream: BinaryIO, suffix: str) -> str:
    """Stream binary upload to disk sem carregar na RAM."""
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with open(fd, "wb") as dest:
            shutil.copyfileobj(upload_stream, dest, length=65_536)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
    return tmp_path


def _read_text_safe(raw_bytes: bytes) -> str:
    """Lê bytes como UTF-8 com fallback e sanitização de null bytes."""
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")
    return text.replace("\x00", "")


@router.post("/ingest", response_class=HTMLResponse)
async def ui_ingest(
    request: Request,
    background_tasks: BackgroundTasks,
    project_id: UUID = Form(...),
    title: str | None = Form(None),
    content: str | None = Form(None),
    source_type: str = Form(...),
    files: list[UploadFile] | None = File(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Handle document ingestion via paste ou file upload."""
    docs: list[KnowledgeDocument] = []

    if files:
        for upload in files:
            if not upload or not upload.filename:
                continue

            filename = upload.filename
            content_type = (upload.content_type or "").lower()
            final_title = (title or "").strip() or filename

            is_binary = "pdf" in content_type or filename.lower().endswith(".pdf")

            if is_binary:
                suffix = Path(filename).suffix.lower() or ".bin"
                _ = await asyncio.to_thread(
                    _stream_to_tempfile, upload.file, suffix
                )
                # Para PDFs, extrair texto seria feito no processamento em background
                doc = KnowledgeDocument(
                    project_id=project_id,
                    title=final_title,
                    source_type=source_type,
                    status="PROCESSING",
                )
            else:
                raw_bytes = await upload.read()

                if len(raw_bytes) > MAX_TEXT_MATERIALIZATION_BYTES:
                    error_html = (
                        "<div class='rounded-lg bg-red-50 px-3 py-2 text-sm "
                        f"font-medium text-red-800'>File '{filename}' exceeds "
                        f"{MAX_TEXT_MATERIALIZATION_BYTES // (1024 * 1024)}MB "
                        "limit for text files.</div>"
                    )
                    return HTMLResponse(content=error_html)

                final_content = _read_text_safe(raw_bytes)
                doc = KnowledgeDocument(
                    project_id=project_id,
                    title=final_title,
                    content=final_content,
                    source_type=source_type,
                    status="PROCESSING",
                )

            db.add(doc)
            await db.flush()
            await db.refresh(doc)
            docs.append(doc)

        await db.commit()

        for doc in docs:
            background_tasks.add_task(process_document_task, doc.id)

        template_str = (
            "{% from 'snippets.html' import status_polling %}"
            "{% for d in docs %}{{ status_polling(d.id, 'PROCESSING') }}{% endfor %}"
        )
        html = templates.env.from_string(template_str).render(docs=docs)
        return HTMLResponse(content=html)

    if not content or not (title or "").strip():
        error_html = (
            "<div class='rounded-lg bg-red-50 px-3 py-2 text-sm "
            "font-medium text-red-800'>Preencha título e conteúdo "
            "ou anexe um arquivo.</div>"
        )
        return HTMLResponse(content=error_html)

    final_title = title.strip() if title else ""
    final_content = (content or "").replace("\x00", "")

    doc = KnowledgeDocument(
        project_id=project_id,
        title=final_title,
        content=final_content,
        source_type=source_type,
        status="PROCESSING",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    await db.commit()

    background_tasks.add_task(process_document_task, doc.id)

    template_str = (
        "{% from 'snippets.html' import status_polling %}"
        "{{ status_polling(doc_id, 'PROCESSING') }}"
    )
    html = templates.env.from_string(template_str).render(doc_id=doc.id)
    return HTMLResponse(content=html)


@router.get("/status/{document_id}", response_class=HTMLResponse)
async def ui_status(
    request: Request,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Poll document processing status para HTMX."""
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
    result = await db.execute(stmt)
    doc: KnowledgeDocument | None = result.scalar_one_or_none()

    if not doc:
        return HTMLResponse(
            content="<div class='text-red-500'>Document not found</div>",
        )

    status_value = doc.status
    error_msg: str | None = None

    if status_value == "PROCESSING":
        time_diff = datetime.now(UTC) - doc.created_at
        if time_diff.total_seconds() > 600:
            status_value = "ERROR"
            error_msg = "Processing timeout (10m exceeded). Please re-ingest."

    if status_value == "ERROR" and error_msg is None:
        error_msg = doc.error_message

    template_str = (
        "{% from 'snippets.html' import status_polling %}"
        "{{ status_polling(doc_id, status, error) }}"
    )
    html = templates.env.from_string(template_str).render(
        doc_id=document_id,
        status=status_value,
        error=error_msg,
    )
    return HTMLResponse(content=html)


@router.post("/query", response_class=HTMLResponse)
async def ui_query(
    request: Request,
    project_id: UUID = Form(...),
    question: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Executa query RAG via HTMX UI."""
    try:
        result = await query_rag(db, project_id, question)

        if result is None:
            return HTMLResponse(
                "<div class='text-red-500'>No documents found. Ingest one first.</div>",
            )

        template_str = (
            "{% from 'snippets.html' import qa_answer %}{{ qa_answer(answer) }}"
        )
        html = templates.env.from_string(template_str).render(answer=result)
        return HTMLResponse(content=html)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(
            f"<div class='text-red-500'>Error querying: {exc}</div>",
        )
