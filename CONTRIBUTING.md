# Contributing

Thanks for contributing to Prumo Lite.

## Development Setup

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
```

Run the API locally:

```bash
uv run uvicorn app.main:app --reload
```

## Adding New Documentation Sources

The Stellar ingestion flow lives in `app/adapters/stellar_crawler.py` and `scripts/ingest_stellar_docs.py`.

To add a new source:

1. Extend the crawler with a new fetch function or add a new repository to the allowlist.
2. Make sure every crawled document includes `title`, `content`, `source_url`, and `source_type`.
3. Filter noisy pages early. Changelogs, release notes, generated API dumps, and duplicated content usually hurt retrieval quality.
4. Keep retries, timeouts, and logging in place so batch ingestion remains resilient.

## Improving the Chat Prompt

The Stellar chat behavior is defined in `app/services/chat_service.py`.

When changing the prompt:

1. Preserve the retrieval-grounded behavior.
2. Keep the Web2 analogy first.
3. Prefer short, practical answers over long essays.
4. Do not ask Gemini to invent sources. Source references come from retrieved documents.

## Running Tests

Run the focused suite:

```bash
uv run pytest tests/test_knowledge_query_service.py tests/test_stellar_chat.py tests/test_stellar_crawler.py
```

Run the full checks:

```bash
uv run pytest
uv run ruff check .
uv run mypy .
```

## Pull Requests

Before opening a pull request:

1. Keep changes focused on a single concern.
2. Add or update tests for behavior changes.
3. Make sure linting, typing, and tests pass locally.
4. Explain the motivation and the user-facing impact in the PR description.
