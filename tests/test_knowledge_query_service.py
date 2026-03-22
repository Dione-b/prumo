from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.knowledge_query_service import KnowledgeQueryService


class _FakeResult:
    def __init__(self, rows: list[tuple[object, float]]):
        self._rows = rows

    def all(self) -> list[tuple[object, float]]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[tuple[object, float]]):
        self._rows = rows

    async def execute(self, _stmt: object) -> _FakeResult:
        return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_retrieve_documents_returns_ranked_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid4()
    document_id = uuid4()
    fake_document = SimpleNamespace(
        id=document_id,
        title="Stellar Accounts",
        source_url="https://developers.stellar.org/docs/learn/fundamentals/stellar-data-structures/accounts",
        content="A Stellar account stores balances and signers.",
    )
    service = KnowledgeQueryService(
        cast(AsyncSession, _FakeSession([(fake_document, 0.12)]))
    )

    async def fake_generate_embedding(_query: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(
        "app.services.knowledge_query_service.generate_embedding",
        fake_generate_embedding,
    )

    documents = await service.retrieve_documents(
        project_id=project_id,
        query="account",
    )

    assert len(documents) == 1
    assert documents[0].document_id == document_id
    assert documents[0].title == "Stellar Accounts"
    assert documents[0].distance == pytest.approx(0.12)
    assert "balances" in documents[0].snippet


@pytest.mark.asyncio
async def test_answer_question_returns_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = uuid4()
    document_id = uuid4()
    fake_document = SimpleNamespace(
        id=document_id,
        title="What Is Soroban",
        source_url=(
            "https://developers.stellar.org/docs/build/smart-contracts/overview"
        ),
        content="Soroban is Stellar smart contract platform for predictable fees.",
    )
    service = KnowledgeQueryService(
        cast(AsyncSession, _FakeSession([(fake_document, 0.08)]))
    )

    async def fake_generate_embedding(_query: str) -> list[float]:
        return [0.4, 0.5, 0.6]

    def fake_generate_answer(_prompt: str) -> SimpleNamespace:
        return SimpleNamespace(
            text=json.dumps(
                {
                    "answer": "Soroban lets developers run smart contracts on Stellar.",
                    "confidence_level": "HIGH",
                }
            )
        )

    monkeypatch.setattr(
        "app.services.knowledge_query_service.generate_embedding",
        fake_generate_embedding,
    )
    monkeypatch.setattr(service, "_generate_answer", fake_generate_answer)

    response = await service.answer_question(
        project_id=project_id,
        query="What is Soroban?",
    )

    assert "smart contracts" in response.answer
    assert response.confidence_level == "HIGH"
    assert len(response.citations) == 1
    assert response.citations[0].document_id == document_id
    assert response.citations[0].source == "What Is Soroban"


@pytest.mark.asyncio
async def test_answer_question_without_documents_returns_low_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = KnowledgeQueryService(cast(AsyncSession, _FakeSession([])))

    async def fake_generate_embedding(_query: str) -> list[float]:
        return [0.0, 0.0, 0.0]

    monkeypatch.setattr(
        "app.services.knowledge_query_service.generate_embedding",
        fake_generate_embedding,
    )

    response = await service.answer_question(
        project_id=uuid4(),
        query="Unknown question",
    )

    assert response.confidence_level == "LOW"
    assert response.citations == []
    assert "READY" in response.answer
