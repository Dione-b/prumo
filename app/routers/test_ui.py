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
# Do not expose to public network without adding CSRF middleware.

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
from app.models.graph import GraphNode
from app.models.knowledge import KnowledgeDocument
from app.models.project import Project
from app.schemas.knowledge import (
    CacheRefreshingResponse,
    DocumentIngestRequest,
    QueryMode,
)
from app.services.file_classifier import (
    MAX_TEXT_MATERIALIZATION_BYTES,
    get_upload_mime,
    is_binary_file,
)
from app.services.knowledge_orchestrator import (
    orchestrate_batch_ingestion,
    orchestrate_query,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/ui", tags=["UI Testbed"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Render the HTMX test dashboard.

    Read-only: fetches all projects for the dropdown
    and aggregate counts for the top bar.
    No inserts, no commits — compliant with C_03_UoW.
    """
    result = await db.execute(select(Project).order_by(Project.created_at))
    projects = result.scalars().all()

    doc_count_result = await db.execute(select(func.count(KnowledgeDocument.id)))
    doc_count = doc_count_result.scalar_one()

    node_count_result = await db.execute(select(func.count(GraphNode.id)))
    node_count = node_count_result.scalar_one()

    # Load recent documents for data management tab
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
            "node_count": node_count,
            "recent_docs": recent_docs,
        },
    )


def _stream_to_tempfile(upload_stream: BinaryIO, suffix: str) -> str:
    """Stream binary upload directly to a temp file without loading into RAM.

    Uses shutil.copyfileobj with a 64KB buffer to keep memory usage constant
    regardless of file size.

    Args:
        upload_stream: The file-like object from UploadFile (upload.file).
        suffix: File extension (e.g. ".pdf").

    Returns:
        Absolute path of the created temp file.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with open(fd, "wb") as dest:
            shutil.copyfileobj(upload_stream, dest, length=65_536)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
    return tmp_path


def _read_text_safe(raw_bytes: bytes) -> str:
    """Read bytes as UTF-8 text with fallback and null byte sanitization.

    Strips '\x00' (null bytes) that cause CharacterNotInRepertoireError
    in PostgreSQL when persisted to TEXT/VARCHAR columns.

    Args:
        raw_bytes: Raw file bytes.

    Returns:
        Sanitized text content.
    """
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("latin-1")

    # Guard against null bytes that slip through mixed encodings.
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
    """Handle document ingestion via paste or file upload.

    Supports single and multi-file uploads. For binary files (PDF/DOCX),
    the upload is streamed directly to disk without loading into RAM.
    raw_content stays NULL in the database — the background task reads
    from the temp file via streaming.
    """
    docs: list[KnowledgeDocument] = []

    if files:
        ingest_requests: list[DocumentIngestRequest] = []
        for upload in files:
            if not upload or not upload.filename:
                continue

            filename = upload.filename
            content_type = (upload.content_type or "").lower()
            binary = is_binary_file(content_type, filename)

            final_title = (title or "").strip() or filename

            if binary:
                # STREAMING PATH: Never call read(). Stream directly to disk.
                suffix = Path(filename).suffix.lower() or ".bin"
                tmp_path = await _stream_binary_to_disk(upload, suffix)

                upload_mime = get_upload_mime(content_type, filename)

                ingest_req = DocumentIngestRequest(
                    project_id=project_id,
                    title=final_title,
                    content=None,  # raw_content = NULL in the database
                    source_type=source_type,
                    metadata={
                        "is_binary_upload": True,
                        "source_filename": filename,
                        "content_type": upload_mime,
                        "temp_file_path": tmp_path,
                        "file_suffix": suffix,
                    },
                )
            else:
                # TEXT PATH: Materialize with a 10MB limit and sanitize null bytes.
                raw_bytes = await upload.read()

                if len(raw_bytes) > MAX_TEXT_MATERIALIZATION_BYTES:
                    logger.warning(
                        "text_file_exceeds_limit",
                        filename=filename,
                        size_bytes=len(raw_bytes),
                        limit=MAX_TEXT_MATERIALIZATION_BYTES,
                    )
                    error_html = (
                        "<div class='rounded-lg bg-red-50 px-3 py-2 text-sm "
                        f"font-medium text-red-800'>File '{filename}' exceeds "
                        f"{MAX_TEXT_MATERIALIZATION_BYTES // (1024 * 1024)}MB "
                        "limit for text files.</div>"
                    )
                    return HTMLResponse(content=error_html)

                final_content = _read_text_safe(raw_bytes)

                ingest_req = DocumentIngestRequest(
                    project_id=project_id,
                    title=final_title,
                    content=final_content,
                    source_type=source_type,
                    metadata=None,
                )

            ingest_requests.append(ingest_req)

        if not ingest_requests:
            error_html = (
                "<div class='rounded-lg bg-red-50 px-3 py-2 text-sm "
                "font-medium text-red-800'>Nenhum arquivo válido foi selecionado.</div>"
            )
            return HTMLResponse(content=error_html)

        docs = await orchestrate_batch_ingestion(ingest_requests, background_tasks, db)

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
    # Sanitize null bytes even in textarea input.
    final_content = (content or "").replace("\x00", "")

    ingest_req = DocumentIngestRequest(
        project_id=project_id,
        title=final_title,
        content=final_content,
        source_type=source_type,
        metadata=None,
    )
    docs = await orchestrate_batch_ingestion([ingest_req], background_tasks, db)
    doc = docs[0]

    template_str = (
        "{% from 'snippets.html' import status_polling %}"
        "{{ status_polling(doc_id, 'PROCESSING') }}"
    )
    html = templates.env.from_string(template_str).render(doc_id=doc.id)
    return HTMLResponse(content=html)


async def _stream_binary_to_disk(upload: UploadFile, suffix: str) -> str:
    """Stream binary to disk via asyncio.to_thread to avoid blocking the event loop.

    Args:
        upload: FastAPI UploadFile object.
        suffix: File extension (e.g. ".pdf").

    Returns:
        Absolute path of the temp file.
    """
    return await asyncio.to_thread(_stream_to_tempfile, upload.file, suffix)


@router.get("/status/{document_id}", response_class=HTMLResponse)
async def ui_status(
    request: Request,
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Poll document processing status for HTMX."""
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
        if doc.metadata_json and "error" in doc.metadata_json:
            error_msg = str(doc.metadata_json["error"])

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


@router.post("/reprocess/{document_id}", response_class=HTMLResponse)
async def ui_reprocess(
    request: Request,
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Reprocess a document stuck in READY_PARTIAL."""
    from app.services.knowledge_gemini import process_document_task

    stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if doc and doc.status == "READY_PARTIAL":
        doc.status = "PROCESSING"
        await db.commit()
        background_tasks.add_task(process_document_task, doc.id)

    template_str = (
        "{% from 'snippets.html' import status_polling %}"
        "{{ status_polling(doc_id, 'PROCESSING') }}"
    )
    html = templates.env.from_string(template_str).render(doc_id=document_id)
    return HTMLResponse(content=html)


@router.post("/query", response_class=HTMLResponse)
async def ui_query(
    request: Request,
    background_tasks: BackgroundTasks,
    project_id: UUID = Form(...),
    question: str = Form(...),
    mode: QueryMode = Form("hybrid"),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Execute a knowledge query from the HTMX UI."""
    try:
        result = await orchestrate_query(
            project_id,
            question,
            background_tasks,
            db,
            mode=mode,
        )

        if result is None:
            return HTMLResponse(
                "<div class='text-red-500'>No documents found. Ingest one first.</div>",
            )

        if isinstance(result, CacheRefreshingResponse):
            if result.status == "PROCESSING_WAIT":
                return HTMLResponse(
                    "<div class='text-yellow-500'>Documents are still processing. "
                    "Please wait.</div>",
                )

            template_str = (
                "{% from 'snippets.html' import qa_refreshing %}"
                "{{ qa_refreshing(project_id, question, mode) }}"
            )
            html = templates.env.from_string(template_str).render(
                project_id=project_id,
                question=question,
                mode=mode,
            )
            return HTMLResponse(content=html)

        template_str = (
            "{% from 'snippets.html' import qa_answer %}{{ qa_answer(answer) }}"
        )
        html = templates.env.from_string(template_str).render(answer=result)
        return HTMLResponse(content=html)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(
            f"<div class='text-red-500'>Error querying Gemini: {exc}</div>",
        )
