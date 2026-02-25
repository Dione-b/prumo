from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError
from app.logger import setup_logging
from app.routers import ingest, knowledge, projects, test_ui

setup_logging()

app = FastAPI(
    title="Prumo API",
    description="Context orchestration engine for agentic IDEs",
    version="0.1.0",
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
