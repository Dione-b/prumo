# TECH_DEBT_003: WARNING - No CSRF protection. Bind to 127.0.0.1 only.
# Do not expose to public network without adding CSRF middleware.

from datetime import UTC, datetime
from uuid import UUID

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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import CacheRefreshingResponse, DocumentIngestRequest
from app.services.knowledge_orchestrator import (
    orchestrate_ingestion,
    orchestrate_query,
)

router = APIRouter(prefix="/ui", tags=["UI Testbed"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the HTMX test dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})


def _read_upload_content(upload: UploadFile) -> str:
    """Read file content with UTF-8 fallback to latin-1."""
    raw = upload.file.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


@router.post("/ingest", response_class=HTMLResponse)
async def ui_ingest(
    request: Request,
    background_tasks: BackgroundTasks,
    project_id: UUID = Form(...),
    title: str | None = Form(None),
    content: str | None = Form(None),
    source_type: str = Form(...),
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Handle document ingestion: paste (title+content) or file upload."""
    if file and file.filename:
        content_from_file = _read_upload_content(file)
        final_title = (title or "").strip() or file.filename
        final_content = content_from_file
    else:
        if not content or not (title or "").strip():
            error_html = (
                "<div class='rounded-lg bg-red-50 px-3 py-2 text-sm "
                "font-medium text-red-800'>Preencha título e conteúdo "
                "ou anexe um arquivo.</div>"
            )
            return HTMLResponse(content=error_html)
        final_title = title.strip() if title else ""
        final_content = content or ""

    ingest_req = DocumentIngestRequest(
        project_id=project_id,
        title=final_title,
        content=final_content,
        source_type=source_type,
    )
    doc, _ = await orchestrate_ingestion(ingest_req, background_tasks, db)

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


@router.post("/query", response_class=HTMLResponse)
async def ui_query(
    request: Request,
    background_tasks: BackgroundTasks,
    project_id: UUID = Form(...),
    question: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Execute a knowledge query from the HTMX UI."""
    try:
        result = await orchestrate_query(project_id, question, background_tasks, db)

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
                "{{ qa_refreshing(project_id, question) }}"
            )
            html = templates.env.from_string(template_str).render(
                project_id=project_id,
                question=question,
            )
            return HTMLResponse(content=html)

        template_str = (
            "{% from 'snippets.html' import qa_answer %}"
            "{{ qa_answer(answer) }}"
        )
        html = templates.env.from_string(template_str).render(answer=result)
        return HTMLResponse(content=html)
    except Exception as exc:  # noqa: BLE001
        return HTMLResponse(
            f"<div class='text-red-500'>Error querying Gemini: {exc}</div>",
        )

