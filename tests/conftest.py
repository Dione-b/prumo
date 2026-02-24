from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app as _app


@pytest_asyncio.fixture()
async def app() -> FastAPI:
    """Fixture to provide the FastAPI application."""
    return _app


@pytest_asyncio.fixture()
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an async test client."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture()
def mock_db() -> AsyncMock:
    """Provide a mock AsyncSession that bypassed the actual DB."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture(autouse=True)
def override_db_dependency(app: FastAPI, mock_db: AsyncMock) -> None:
    """Override the FastAPI get_db dependency to use the mock."""
    app.dependency_overrides[get_db] = lambda: mock_db
