"""
Ingere docs oficiais da Stellar e SDKs GitHub no pgvector.

Requisito: a API Prumo precisa estar no ar (padrao http://localhost:8000).
    uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Uso:
    uv run python scripts/ingest_stellar_docs.py
    uv run python scripts/ingest_stellar_docs.py --source docs
    uv run python scripts/ingest_stellar_docs.py --source github

Outro host/porta: export PRUMO_API_BASE_URL=http://127.0.0.1:9000
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
import structlog

# Permite `uv run python scripts/ingest_stellar_docs.py` com o pacote `app` na raiz.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.adapters.stellar_crawler import (  # noqa: E402
    CrawledDocument,
    crawl_stellar_docs,
    crawl_stellar_github_repos,
)

logger = structlog.get_logger(__name__)

BASE_URL = os.getenv("PRUMO_API_BASE_URL", "http://localhost:8000")
PROJECT_NAME = "stellar-docs"
PROJECT_DESCRIPTION = "Documentacao oficial da Stellar e SDKs"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=["docs", "github"],
        default=None,
        help="Seleciona uma fonte especifica de ingestao.",
    )
    return parser.parse_args()


async def _require_running_api(client: httpx.AsyncClient) -> None:
    """Falha com mensagem clara se nada estiver escutando em BASE_URL."""
    try:
        response = await client.get("/health", timeout=15.0)
        response.raise_for_status()
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        print(
            f"Erro: nao foi possivel conectar a API em {BASE_URL!r} ({exc}).",
            file=sys.stderr,
        )
        print(
            "\nSuba o servidor antes de rodar a ingestao, por exemplo:\n"
            "  uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000\n\n"
            "Se a API estiver em outro endereco, defina a variavel PRUMO_API_BASE_URL.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


async def _get_or_create_project(client: httpx.AsyncClient) -> UUID:
    response = await client.get("/projects")
    response.raise_for_status()
    projects = response.json()

    for project in projects:
        if project["name"] == PROJECT_NAME:
            project_id = UUID(project["id"])
            logger.info("stellar_project_found", project_id=str(project_id))
            return project_id

    response = await client.post(
        "/projects",
        json={"name": PROJECT_NAME, "description": PROJECT_DESCRIPTION},
    )
    response.raise_for_status()
    project = response.json()
    project_id = UUID(project["id"])
    logger.info("stellar_project_created", project_id=str(project_id))
    return project_id


async def _collect_documents(
    source: Literal["docs", "github"] | None,
) -> list[CrawledDocument]:
    if source == "docs":
        return await crawl_stellar_docs()
    if source == "github":
        return await crawl_stellar_github_repos()

    docs, github_docs = await asyncio.gather(
        crawl_stellar_docs(),
        crawl_stellar_github_repos(),
    )
    return [*docs, *github_docs]


async def _ingest_documents(
    client: httpx.AsyncClient,
    *,
    project_id: UUID,
    documents: list[CrawledDocument],
) -> tuple[int, int]:
    success_count = 0
    total_characters = 0

    for index, document in enumerate(documents, start=1):
        payload = {
            "project_id": str(project_id),
            "title": document["title"],
            "content": document["content"],
            "source_type": document["source_type"],
            "source_url": document["source_url"],
        }

        try:
            response = await client.post("/knowledge/documents", json=payload)
            response.raise_for_status()
            success_count += 1
            total_characters += len(document["content"])
            logger.info(
                "stellar_document_ingested",
                index=index,
                total=len(documents),
                title=document["title"],
                source_type=document["source_type"],
            )
        except Exception as exc:
            logger.warning(
                "stellar_document_ingest_failed",
                index=index,
                total=len(documents),
                title=document["title"],
                error=str(exc),
            )

    return success_count, total_characters


async def main() -> None:
    args = _parse_args()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        await _require_running_api(client)
        project_id = await _get_or_create_project(client)
        documents = await _collect_documents(args.source)

        logger.info(
            "stellar_documents_collected",
            total_documents=len(documents),
            source=args.source or "all",
            stellar_project_id=str(project_id),
        )

        success_count, total_characters = await _ingest_documents(
            client,
            project_id=project_id,
            documents=documents,
        )

    print(f"STELLAR_PROJECT_ID={project_id}")
    print(
        "Ingestion summary:",
        {
            "documents_collected": len(documents),
            "documents_ingested": success_count,
            "approx_chunks": success_count,
            "total_characters": total_characters,
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
