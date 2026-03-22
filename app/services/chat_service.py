from __future__ import annotations

import asyncio
from typing import Final
from uuid import UUID

import structlog
from google import genai
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.schemas.chat import ChatMessage, SourceReference
from app.services.knowledge_query_service import (
    KnowledgeQueryService,
    RetrievedDocument,
    _extract_response_text,
)

logger = structlog.get_logger(__name__)
client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

MAX_HISTORY_MESSAGES: Final[int] = 10

STELLAR_CHAT_SYSTEM_PROMPT = """You are a Stellar blockchain expert helping Web2
developers understand the Stellar network.

Rules for every response:
1. Always start with a Web2 analogy when introducing a new concept.
2. Explain WHY before HOW.
3. Structure your answer as: Concept -> Analogy -> Code Example (when applicable).
4. Never use jargon without explaining it first.
5. Keep answers concise and practical.
6. If you do not know something from the provided context, say so clearly.
7. Cite facts only when grounded in the provided Stellar documentation context.
"""


class _ChatSynthesisResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str


class StellarChatService:
    def __init__(self, db: AsyncSession):
        self._knowledge_service = KnowledgeQueryService(db)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        reraise=True,
    )
    async def answer(
        self,
        *,
        question: str,
        history: list[ChatMessage],
        project_id: UUID,
    ) -> tuple[str, list[SourceReference]]:
        documents = await self._knowledge_service.retrieve_documents(
            project_id=project_id,
            query=question,
            limit=5,
        )
        if not documents:
            return (
                "Pense na falta de contexto como consultar um banco sem ter "
                "acesso ao extrato: eu nao tenho documentacao suficiente nesta "
                "base para responder com seguranca.",
                [],
            )

        prompt = self._build_prompt(
            question=question,
            history=history,
            documents=documents,
        )
        response = await asyncio.to_thread(self._generate_answer, prompt)
        payload = _ChatSynthesisResponse.model_validate_json(
            _extract_response_text(response)
        )

        unique_sources: list[SourceReference] = []
        seen_sources: set[tuple[str, str]] = set()
        for document in documents:
            source_key = (
                document.title,
                document.source_url or f"document:{document.document_id}",
            )
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)
            unique_sources.append(
                SourceReference(
                    title=document.title,
                    source_url=source_key[1],
                )
            )

        logger.info(
            "stellar_chat_answered",
            project_id=str(project_id),
            sources=len(unique_sources),
        )
        return payload.answer.strip(), unique_sources

    def _build_prompt(
        self,
        *,
        question: str,
        history: list[ChatMessage],
        documents: list[RetrievedDocument],
    ) -> str:
        history_lines = [
            f"{message.role.upper()}: {message.content.strip()}"
            for message in history[-MAX_HISTORY_MESSAGES:]
        ]
        history_block = (
            "\n".join(history_lines) if history_lines else "No prior history."
        )

        context_block = "\n\n".join(
            [
                "\n".join(
                    [
                        f"[Source {index}]",
                        f"Title: {document.title}",
                        f"URL: {document.source_url or 'N/A'}",
                        f"Snippet: {document.snippet}",
                        f"Content:\n{document.content}",
                    ]
                )
                for index, document in enumerate(documents, start=1)
            ]
        )

        return "\n\n".join(
            [
                "Conversation history:",
                history_block,
                "Retrieved Stellar documentation context:",
                context_block,
                f"Current user question: {question}",
            ]
        )

    def _generate_answer(self, prompt: str) -> object:
        return client.models.generate_content(
            model=settings.gemini_synthesis_model,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_ChatSynthesisResponse,
                temperature=settings.gemini_temperature,
                system_instruction=STELLAR_CHAT_SYSTEM_PROMPT,
            ),
        )
