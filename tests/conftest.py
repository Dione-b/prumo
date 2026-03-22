from __future__ import annotations

import os
from uuid import uuid4

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://prumo:prumo@localhost:5432/prumo_test",
)
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("STELLAR_PROJECT_ID", str(uuid4()))
