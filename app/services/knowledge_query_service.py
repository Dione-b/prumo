from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal, cast
from uuid import UUID

import structlog
from google import genai
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.models.knowledge import KnowledgeDocument
from app.schemas.knowledge import AnswerCitation, KnowledgeAnswer
from app.services.recipe_extractor import generate_embedding

logger = structlog.get_logger(__name__)
client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

KNOWLEDGE_SYSTEM_PROMPT = """You are a retrieval-grounded assistant.

Answer only from the provided context.
If the context is insufficient, say that clearly.
Keep the answer concise, accurate, and practical.
Do not invent sources or facts that are not present in the context.
"""


@dataclass(frozen=True)
class RetrievedDocument:
    document_id: UUID
    title: str
    source_url: str | None
    content: str
    snippet: str
    distance: float


class _KnowledgeSynthesisResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    confidence_level: str


def _build_snippet(content: str, max_length: int = 320) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3].rstrip()}..."


def _coerce_confidence(value: str) -> Literal["HIGH", "MEDIUM", "LOW"]:
    normalized = value.strip().upper()
    if normalized in {"HIGH", "MEDIUM", "LOW"}:
        return cast(Literal["HIGH", "MEDIUM", "LOW"], normalized)
    return "LOW"


def _extract_response_text(response: object) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    msg = "Gemini returned an empty response."
    raise ValueError(msg)


class KnowledgeQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def retrieve_documents(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int = 5,
    ) -> list[RetrievedDocument]:
        query_embedding = await generate_embedding(query)

        distance_expr = KnowledgeDocument.embedding.l2_distance(query_embedding)
        stmt: Select[tuple[KnowledgeDocument, float]] = (
            select(KnowledgeDocument, distance_expr)
            .where(KnowledgeDocument.project_id == project_id)
            .where(KnowledgeDocument.status == "READY")
            .where(KnowledgeDocument.embedding.is_not(None))
            .where(KnowledgeDocument.content.is_not(None))
            .order_by(distance_expr)
            .limit(limit)
        )
        result = await self.db.execute(stmt)

        documents: list[RetrievedDocument] = []
        for row in result.all():
            document = row[0]
            distance = float(row[1])
            content = document.content or ""
            documents.append(
                RetrievedDocument(
                    document_id=document.id,
                    title=document.title,
                    source_url=document.source_url,
                    content=content,
                    snippet=_build_snippet(content),
                    distance=distance,
                )
            )
        return documents

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        reraise=True,
    )
    async def answer_question(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int = 5,
    ) -> KnowledgeAnswer:
        documents = await self.retrieve_documents(
            project_id=project_id,
            query=query,
            limit=limit,
        )
        if not documents:
            return KnowledgeAnswer(
                answer=(
                    "Nao ha documentos prontos para busca vetorial neste projeto "
                    "(e necessario status READY e embedding preenchido). "
                    "Se a ingestao acabou de rodar, aguarde o processamento em "
                    "background (Gemini + embedding). "
                    f"Diagnostico: GET /knowledge/projects/{project_id}/summary"
                ),
                confidence_level="LOW",
                citations=[],
            )

        context_blocks = []
        citations: list[AnswerCitation] = []
        for index, document in enumerate(documents, start=1):
            context_blocks.append(
                "\n".join(
                    [
                        f"[Source {index}]",
                        f"Title: {document.title}",
                        f"URL: {document.source_url or 'N/A'}",
                        f"Snippet: {document.snippet}",
                        f"Content:\n{document.content}",
                    ]
                )
            )
            citations.append(
                AnswerCitation(
                    document_id=document.document_id,
                    snippet=document.snippet,
                    source=document.title,
                )
            )

        prompt = "\n\n".join(
            [
                "Use the retrieved context below to answer the user question.",
                "Context:",
                "\n\n".join(context_blocks),
                f"Question: {query}",
            ]
        )

        response = await asyncio.to_thread(self._generate_answer, prompt)
        payload = _KnowledgeSynthesisResponse.model_validate_json(
            _extract_response_text(response)
        )

        logger.info(
            "knowledge_query_answered",
            project_id=str(project_id),
            citations=len(citations),
            confidence=_coerce_confidence(payload.confidence_level),
        )

        return KnowledgeAnswer(
            answer=payload.answer.strip(),
            confidence_level=_coerce_confidence(payload.confidence_level),
            citations=citations,
        )

    def _generate_answer(self, prompt: str) -> object:
        return client.models.generate_content(
            model=settings.gemini_synthesis_model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_KnowledgeSynthesisResponse,
                temperature=settings.gemini_temperature,
                system_instruction=KNOWLEDGE_SYSTEM_PROMPT,
            ),
        )
