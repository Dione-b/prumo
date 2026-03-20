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


import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.application.use_cases import (
    IngestBusinessResult,
    ProjectNotFoundError,
)
from app.composition import provide_ingest_business_use_case
from app.config import settings
from app.domain.entities import BusinessRuleExtraction, BusinessRuleRecord


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


class FakeIngestBusinessUseCase:
    def __init__(self, result: IngestBusinessResult | None = None) -> None:
        self._result = result

    async def execute(
        self,
        *,
        project_id: uuid.UUID,
        raw_text: str,
        source: str | None,
    ) -> IngestBusinessResult:
        if self._result is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        return self._result


def _build_result(project_id: str) -> IngestBusinessResult:
    extraction = BusinessRuleExtraction(
        client_name="Test Company",
        core_objective="Manage users",
        technical_constraints=("Postgres",),
        acceptance_criteria=("Users can log in",),
        additional_notes="None",
        confidence_level="HIGH",
        warnings=(),
    )
    record = BusinessRuleRecord(
        id=uuid.uuid4(),
        project_id=uuid.UUID(project_id),
        raw_text="We need to build a system that manages users using Postgres.",
        client_name=extraction.client_name,
        core_objective=extraction.core_objective,
        technical_constraints=extraction.technical_constraints,
        acceptance_criteria=extraction.acceptance_criteria,
        additional_notes=extraction.additional_notes,
        confidence_level=extraction.confidence_level,
        source="Meeting notes.txt",
    )
    return IngestBusinessResult(record=record, extraction=extraction)


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
    app: FastAPI,
    client: httpx.AsyncClient,
    valid_payload: dict[str, str],
    valid_api_key: str,
) -> None:
    app.dependency_overrides[provide_ingest_business_use_case] = (
        lambda: FakeIngestBusinessUseCase()
    )

    res = await client.post(
        "/ingest/business",
        json=valid_payload,
        headers={"X-API-Key": valid_api_key},
    )

    assert res.status_code == 404
    assert "not found" in res.json()["detail"]
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ingest_business_success(
    app: FastAPI,
    client: httpx.AsyncClient,
    valid_payload: dict[str, str],
    valid_api_key: str,
) -> None:
    app.dependency_overrides[provide_ingest_business_use_case] = (
        lambda: FakeIngestBusinessUseCase(_build_result(valid_payload["project_id"]))
    )

    res = await client.post(
        "/ingest/business",
        json=valid_payload,
        headers={"X-API-Key": valid_api_key},
    )

    assert res.status_code == 200
    data = res.json()
    assert data["saved_in_db"] is True
    assert data["data"]["client_name"] == "Test Company"
    assert "warnings" in data
    app.dependency_overrides.clear()
