# 📐 Prumo

> **Alignment and Precision for Agentic Workflows.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0+-009688.svg)](https://fastapi.tiangolo.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-e92063.svg)](https://docs.pydantic.dev/)
[![Linter](https://img.shields.io/badge/Linter-Ruff-orange.svg)](https://github.com/astral-sh/ruff)
[![Typing](https://img.shields.io/badge/Typing-MyPy-2196F3.svg)](https://mypy-lang.org/)

**Prumo** (Portuguese for _Plumb Line_) is a high-performance context orchestration engine designed for agentic IDEs (like Cursor, Windsurf, or custom AI agents). It acts as the "straight line" that aligns raw, unstructured input with the rigorous requirements of automated development.

It transforms messy data—meeting transcripts, ephemeral notes, and shifting RFCs—into structured business rules and a queryable, semantic knowledge base optimized for RAG (Retrieval-Augmented Generation).

---

## 🛠 Core Pillars

### 1. Semantic Ingestion (Phase 1)

- **Gemini-Powered Extraction**: Leverages Gemini 1.5 Pro to distill structured data (Technical Constraints, Acceptance Criteria, Core Objectives) from unstructured text.
- **Validation-as-Logic**: Uses Pydantic `@model_validator` to provide real-time feedback (warnings on low confidence or missing criteria) before ingestion.
- **Pre-flight Sanitization**: Native LLM JSON generation coupled with robust sanitization to ensure high-fidelity parsing.

### 2. Context Orchestration & RAG (Phase 2)

- **Hybrid Cache Routing**: Orchestrates context using Gemini's **Context Caching** for massive documents and inline RAG for smaller fragments.
- **Async Processing Pipeline**: Heavy uploads and document embeddings run in the background, keeping the API responsive (202 Accepted pattern).
- **pgvector Integration**: Native vector search support for long-term semantic retrieval.

### 3. Developer Experience & Quality

- **HTMX Playground**: A lightweight testing interface at `/ui/` for rapid prototyping without frontend overhead.
- **Rigorous Standard**: 100% type-hinted (MyPy strict) and linted (Ruff) codebase following clean code principles.
- **Autonomous Documentation**: Structured QA responses with confidence levels, citations, and semantic warnings.

---

## 🚀 Tech Stack

- **Core**: FastAPI (Async Python 3.11+)
- **Validation**: Pydantic v2 (Strict typing & validation)
- **Intelligence**: Google Gemini 1.5 Pro (Extraction & Context Caching)
- **Storage**: SQLAlchemy 2.0 + PostgreSQL + `pgvector`
- **Quality**: `ruff` (Linter), `mypy` (Type checking), `pytest` (Test suite)
- **Deployment & Flow**: `uv` (Environment management), `alembic` (Migrations), `tenacity` (Resiliency)

---

## ⚙️ Getting Started

### Prerequisites

- Python 3.11+ and [uv](https://github.com/astral-sh/uv).
- PostgreSQL with `pgvector` (e.g., `pgvector/pgvector:pg16` Docker image).

### Installation

1.  **Sync Environment**:

    ```bash
    uv sync
    ```

2.  **Configure Credentials**:

    ```bash
    cp .env.example .env
    # Set GEMINI_API_KEY, DATABASE_URL, and API_KEY in .env
    ```

3.  **Database Migration**:

    ```bash
    uv run alembic upgrade head
    ```

4.  **Fire it up**:
    ```bash
    uv run uvicorn app.main:app --reload
    ```
    Access the interactive docs at: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Quality & Testing

We maintain high standards through automated checks and comprehensive testing.

- **Run Linters & Checks**:

  ```bash
  uv run ruff check .
  uv run mypy .
  ```

- **Run Test Suite**:
  ```bash
  uv run pytest
  ```

---

## 📖 Usage Highlights

### Ingesting Business Rules

Send raw transcripts; receive structured, validated JSON.

```bash
curl -X 'POST' http://localhost:8000/ingest/business \
  -H 'X-API-Key: <YOUR_KEY>' \
  -d '{"project_id": "...", "raw_text": "we need a python api with jwt auth..."}'
```

### Knowledge Query

Ask questions over the project's knowledge base.

```bash
curl -X 'POST' 'http://localhost:8000/knowledge/query?project_id=...&question=How+is+auth+handled?'
```

---

## 🌐 Language Policy

- **Code & Logic**: 100% English (Architecture, variables, logs, schemas).
- **Data Preservation**: While keys are English, the extracted content preserves the **original language** of the input (Portuguese, Spanish, etc.) to maintain domain fidelity.

---

<p align="center">
  <i>Part of the Prumo Context Orchestration Suite.</i>
</p>
