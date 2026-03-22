from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.schemas.chat import ChatMessage, SourceReference
from app.services.chat_service import StellarChatService
from app.services.knowledge_query_service import RetrievedDocument


@pytest.mark.asyncio
async def test_stellar_chat_service_returns_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_db = cast(AsyncSession, SimpleNamespace())
    service = StellarChatService(fake_db)
    documents = [
        RetrievedDocument(
            document_id=uuid4(),
            title="Stellar Accounts",
            source_url=(
                "https://developers.stellar.org/docs/learn/fundamentals/"
                "stellar-data-structures/accounts"
            ),
            content="Accounts hold balances, signers, and sequence numbers.",
            snippet="Accounts hold balances, signers, and sequence numbers.",
            distance=0.05,
        )
    ]

    async def fake_retrieve_documents(**_kwargs: object) -> list[RetrievedDocument]:
        return documents

    def fake_generate_answer(prompt: str) -> SimpleNamespace:
        assert "USER: How is a Stellar account similar to a bank account?" in prompt
        assert "ASSISTANT: It stores value and authorization data." in prompt
        return SimpleNamespace(
            text=json.dumps(
                {
                    "answer": (
                        "Think of a Stellar account like a bank account, but on a "
                        "shared network. It stores balances and the signing rules "
                        "needed to authorize transactions."
                    )
                }
            )
        )

    monkeypatch.setattr(
        service._knowledge_service,
        "retrieve_documents",
        fake_retrieve_documents,
    )
    monkeypatch.setattr(service, "_generate_answer", fake_generate_answer)

    answer, sources = await service.answer(
        question="What is a Stellar account?",
        history=[
            ChatMessage(
                role="user",
                content="How is a Stellar account similar to a bank account?",
            ),
            ChatMessage(
                role="assistant",
                content="It stores value and authorization data.",
            ),
        ],
        project_id=uuid4(),
    )

    assert "bank account" in answer
    assert len(sources) == 1
    assert sources[0].title == "Stellar Accounts"
    assert sources[0].source_url.startswith("https://developers.stellar.org/")


@pytest.mark.asyncio
async def test_stellar_chat_service_handles_missing_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StellarChatService(cast(AsyncSession, SimpleNamespace()))

    async def fake_retrieve_documents(**_kwargs: object) -> list[RetrievedDocument]:
        return []

    monkeypatch.setattr(
        service._knowledge_service,
        "retrieve_documents",
        fake_retrieve_documents,
    )

    answer, sources = await service.answer(
        question="What is SCP?",
        history=[],
        project_id=uuid4(),
    )

    assert "nao tenho documentacao suficiente" in answer.lower()
    assert sources == []


def test_stellar_chat_endpoint_returns_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield SimpleNamespace()

    async def fake_answer(
        self: StellarChatService,
        **_kwargs: object,
    ) -> tuple[str, list[SourceReference]]:
        del self
        return (
            "Think of Stellar like a payment rail optimized for fast settlement.",
            [
                SourceReference(
                    title="Stellar Overview",
                    source_url=(
                        "https://developers.stellar.org/docs/learn/intro-to-stellar"
                    ),
                )
            ],
        )

    monkeypatch.setattr(StellarChatService, "answer", fake_answer)
    app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(app)
        response = client.post(
            "/chat/stellar",
            json={
                "question": "What is Stellar?",
                "session_id": "session-123",
                "history": [],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "session-123"
    assert "payment rail" in payload["answer"]
    assert payload["sources"][0]["title"] == "Stellar Overview"
