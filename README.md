# 📐 Prumo

> **Alignment and Precision for Agentic Workflows.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0+-009688.svg)](https://fastapi.tiangolo.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-e92063.svg)](https://docs.pydantic.dev/)
[![Linter](https://img.shields.io/badge/Linter-Ruff-orange.svg)](https://github.com/astral-sh/ruff)
[![Typing](https://img.shields.io/badge/Typing-MyPy-2196F3.svg)](https://mypy-lang.org/)

**Prumo** (Portuguese for _Plumb Line_) is a high-performance context orchestration engine designed for agentic IDEs (like Cursor, Windsurf, or custom AI agents). It acts as the "straight line" that aligns raw, unstructured input with the rigorous requirements of automated development.

It transforms messy data—meeting transcripts, ephemeral notes, and shifting RFCs—into structured business rules, a queryable semantic knowledge base, and a **knowledge graph** with community-aware retrieval optimized for RAG (Retrieval-Augmented Generation).

---

## 🛠 Core Pillars

### 1. Semantic Ingestion (Phase 1)

- **Multi-File & Binary Streaming**: Synchronous batch ingestion for raw text, PDFs, and DOCX files. Heavy binaries stream directly to disk without memory spikes. Incorporates real-time `pypdf` extraction to handle latin-1 encoded PDF buffers reliably.
- **Local Native Async Extraction**: Routes structured data extraction (Business Rules) to **Llama 3.2** via a local Ollama instance utilizing the **Ollama 2026 SDK** with Native Tool Calling and automated Pydantic schema conversion.
- **VRAM-Safe Orchestration**: A strict sequential orchestration uses a global semaphore (`max_concurrent=1`) and aggressive model offloading (`keep_alive=0`) to ensure extraction and embeddings never overlap, protecting RTX 2025 GPUs from OOM failures.
- **Thinking & Downgrade Resilience (C_01)**: Captures model `thinking` traces to audit high-fidelity rules. Contradictory reasoning or hardware timeouts trigger graceful degradation, adjusting AI confidence downward instead of breaking the batch.
- **Transactional Consistency (C_03)**: Uses nested DB transactions/savepoints where the background task orchestrator acts as the sole boundary owner.

### 2. Context Orchestration & RAG (Phase 2)

- **Project Context Engine**: Enforces referential integrity by automatically bootstrapping default workspaces on app startup, completely eliminating hardcoded UUIDs.
- **Hybrid Cache Routing**: Orchestrates context using Gemini's **Context Caching** for massive documents and inline RAG for smaller fragments.
- **Async Processing Pipeline**: Heavy document embeddings and processing run smoothly to keep the API responsive.
- **pgvector Integration**: Native vector search support for long-term semantic retrieval.

### 3. Graph-RAG with LightRAG Pattern (Phase 3)

- **Knowledge Graph Extraction**: Automatically extracts semantic entities and relations safely inside background tasks.
- **pgvector HNSW Index**: Entities are locally embedded using **Qwen3 (via Ollama)** and indexed via pgvector HNSW (`m=16`, `ef_construction=64`) for cosine similarity search.
- **Community Detection**: Leiden algorithm (via `leidenalg` + `igraph`) discovers thematic clusters.
- **Three Query Modes**:
  - `local` — Entity-level: pgvector similarity → recursive CTE edge traversal → Pro synthesis.
  - `global` — Community-level: aggregated community summaries → Pro synthesis.
  - `hybrid` (default) — Local first → confidence gating → Global escalation → merge synthesis.
- **Graceful Degradation**: `READY_PARTIAL` status when graph extraction fails but cache is available; hybrid mode falls back to Phase 2 cache routing when the graph is empty.

### 4. Prompt Generation Engine (Phase 3b)

- **Synthesis Engine**: Uses **Gemini 2.5 Pro** via `asyncio.to_thread` to synthesize context and assemble structured YAML prompts for downstream LLM agents.
- **Tiered Strategy**: Classifies tasks as `SIMPLE` (entity-level context) or `COMPLEX` (community context + few-shot examples + code skeletons).
- **Constitutional Constraints**: Injects C_01/C_02/C_03 invariants, project-specific technical constraints, and validation checklists automatically.
- **Confidence-Aware Output**: Confidence is derived from graph availability and auto-downgraded when context is degraded.

### 5. Developer Experience & Quality

- **HTMX Playground**: A lightweight testing interface at `/ui/dashboard` for rapid prototyping with robust CORS and session management.
- **Rigorous Standard**: 100% type-hinted (MyPy strict), linted (Ruff), and backed by a comprehensive test suite (pytest, pytest-mock).
- **Production Hardened**: Built with `tenacity` for resilient Gemini API retries and `structlog` for structured token-usage observability.

---

## 🚀 Tech Stack

| Layer          | Technology                                                                               |
| -------------- | ---------------------------------------------------------------------------------------- |
| **Core**       | FastAPI (Async Python 3.11+)                                                             |
| **Validation** | Pydantic v2 (Strict typing & validation)                                                 |
| **LLM**        | Gemini 2.5 Pro (Synthesis) & Local Ollama (Llama 3.2 / Qwen3 for Edge/Node processing)   |
| **Storage**    | SQLAlchemy 2.0 + PostgreSQL + `pgvector` (HNSW)                                          |
| **Graph**      | `igraph` + `leidenalg` (Leiden community detection)                                      |
| **Quality**    | `ruff` (linter), `mypy` (typing), `pytest` (tests)                                       |
| **Infra**      | `uv` (env), `alembic` (migrations), `tenacity` (resilience), `structlog` (observability) |

---

## 📁 Project Structure

```
app/
├── config.py                           # Settings via pydantic-settings
├── database.py                         # AsyncSession factory
├── main.py                             # FastAPI app + routers
├── models/
│   ├── knowledge.py                    # KnowledgeDocument (File API + Cache)
│   ├── graph.py                        # GraphNode (Vector 768d) + GraphEdge
│   ├── business_rule.py                # BusinessRule
│   └── project.py / plan.py
├── schemas/
│   ├── knowledge.py                    # KnowledgeAnswer, AnswerCitation, QueryMode
│   ├── graph.py                        # EntityExtractionResult, NodeContext, EdgeContext
│   └── prompt_generator.py             # PromptTier, PromptStrategyConfig, GeneratedPrompt
├── utils/
│   └── tool_converter.py               # Pydantic to Ollama Native Tool conversion
├── services/
│   ├── knowledge_gemini.py             # Document pipeline (Branches A+B+C)
│   ├── knowledge_orchestrator.py       # Query routing and batch ingestion handling
│   ├── document_processor.py           # VRAM-Safe orchestrator (Extract -> Embed)
│   ├── ollama_client.py                # Sequential local LLM access + Semaphore
│   ├── graph_extractor.py              # Entity/relation extraction + upsert
│   ├── embedding_service.py            # Local Qwen3 batch embedding
│   ├── community_detector.py           # Leiden + community summaries
│   ├── graph_query_service.py          # Local / Global / Hybrid query engines
│   └── prompt_generator.py             # YAML prompt assembly for LLM agents
└── routers/
    ├── ingest.py                       # /ingest/business multi-file uploads
    ├── knowledge.py                    # /knowledge/documents, /knowledge/query
    ├── projects.py                     # Project contexts and bootstraps
    └── test_ui.py                      # HTMX powered UI routes
```

---

## ⚙️ Getting Started

### Prerequisites

- Python 3.11+ and [uv](https://github.com/astral-sh/uv).
- PostgreSQL with `pgvector` (e.g., `pgvector/pgvector:pg16` Docker image).
- System library `libigraph-dev` (for `leidenalg`).

### Installation

1.  **Sync Environment**:

    ```bash
    uv sync
    ```

2.  **Configure Credentials**:

    ```bash
    cp .env.example .env
    # Set GEMINI_API_KEY, DATABASE_URL, API_KEY and OLLAMA models in .env
    # Note: Ensure an Ollama instance is running locally on port 11434.
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

Ask questions over the project's knowledge base with three query modes.

```bash
# Hybrid (default) — graph + cache fallback
curl -X 'POST' 'http://localhost:8000/knowledge/query?project_id=...&question=How+is+auth+handled?'

# Local — entity-level graph search
curl -X 'POST' 'http://localhost:8000/knowledge/query?project_id=...&question=...&mode=local'

# Global — community-level summaries
curl -X 'POST' 'http://localhost:8000/knowledge/query?project_id=...&question=...&mode=global'
```

---

## 🌐 Language Policy

- **Code & Logic**: 100% English (Architecture, variables, logs, schemas).
- **Data Preservation**: While keys are English, the extracted content preserves the **original language** of the input (Portuguese, Spanish, etc.) to maintain domain fidelity.

---

<p align="center">
  <i>Part of the Prumo Context Orchestration Suite.</i>
</p>
