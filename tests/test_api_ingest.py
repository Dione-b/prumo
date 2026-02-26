import uuid
from collections.abc import AsyncGenerator
from unittest.mock import ANY, AsyncMock

import httpx
import pytest
from pytest_mock import MockerFixture

from app.config import settings
from app.models import Project
from app.schemas.business_rule import BusinessRuleSchema


@pytest.fixture()
def valid_api_key() -> str:
    """Return the statically configured API key."""
    return settings.api_key.get_secret_value()


@pytest.fixture()
def valid_payload() -> dict[str, str]:
    """Provide a minimal valid payload for ingestion."""
    return {
        "project_id": str(uuid.uuid4()),
        "raw_text": "We need to build a system that manages users using Postgres.",
        "source": "Meeting notes.txt",
    }


@pytest.fixture()
async def mock_gemini_extraction(
    mocker: MockerFixture,
) -> AsyncGenerator[AsyncMock, None]:
    """Patch the gemini extraction service avoiding live LLM calls."""
    extracted_data = BusinessRuleSchema(
        client_name="Test Company",
        core_objective="Manage users",
        technical_constraints=["Postgres"],
        acceptance_criteria=["Users can log in"],
        additional_notes="None",
        confidence_level="HIGH",
    )
    patched = mocker.patch(
        "app.routers.ingest.LLMGateway.extract_business_rules",
        return_value=extracted_data,
        autospec=True,
    )
    yield patched


@pytest.mark.asyncio
async def test_ingest_business_missing_api_key(
    client: httpx.AsyncClient, valid_payload: dict[str, str]
) -> None:
    # Act
    res = await client.post("/ingest/business", json=valid_payload)

    # Assert
    assert res.status_code == 401
    assert "missing API key" in res.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_business_invalid_project_id(
    client: httpx.AsyncClient, valid_api_key: str
) -> None:
    # Arrange
    payload = {
        "project_id": "not-a-valid-uuid",
        "raw_text": "Some sufficient text with enough length to pass validation.",
    }

    # Act
    res = await client.post(
        "/ingest/business",
        json=payload,
        headers={"X-API-Key": valid_api_key},
    )

    # Assert
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_ingest_business_project_not_found(
    client: httpx.AsyncClient,
    valid_payload: dict[str, str],
    valid_api_key: str,
    mock_db: AsyncMock,
) -> None:
    # Arrange
    # Service get_project returns None initially
    mock_db.get.return_value = None

    # Act
    res = await client.post(
        "/ingest/business",
        json=valid_payload,
        headers={"X-API-Key": valid_api_key},
    )

    # Assert
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


@pytest.mark.asyncio
async def test_ingest_business_success(
    client: httpx.AsyncClient,
    valid_payload: dict[str, str],
    valid_api_key: str,
    mock_db: AsyncMock,
    mock_gemini_extraction: AsyncMock,
) -> None:
    # Arrange
    # Simulate DB returning a valid Project entity
    mock_project = Project(id=uuid.UUID(valid_payload["project_id"]), name="Test")
    mock_db.get.return_value = mock_project

    # Act
    res = await client.post(
        "/ingest/business",
        json=valid_payload,
        headers={"X-API-Key": valid_api_key},
    )

    # Assert
    assert res.status_code == 200
    data = res.json()
    assert data["saved_in_db"] is True
    assert data["data"]["client_name"] == "Test Company"
    assert "warnings" in data

    # Ensure DB transaction occurred securely
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited_once()
    mock_gemini_extraction.assert_awaited_once_with(
        ANY,
        valid_payload["raw_text"],
        ANY,
    )
