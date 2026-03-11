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

## 🏗 Constitutional Invariants

Three core constraints are enforced across every module:

| Pillar   | Rule                                                                                                                                         |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **C_01** | Confidence downgrades are applied automatically when context is degraded (cache miss, graph unavailable, contradictory thinking traces).     |
| **C_02** | All synchronous SDK calls (`google-genai`, Leiden) are wrapped in `asyncio.to_thread()` to protect the FastAPI event loop.                   |
| **C_03** | Services return pure DTOs — they never call `session.commit()`. Transaction boundaries belong exclusively to routers and task orchestrators. |

---

## 🛠 Core Pillars

### 1. Semantic Ingestion (Phase 1)

- **Multi-File & Binary Streaming**: Synchronous batch ingestion for raw text, PDFs, and DOCX files. Heavy binaries stream directly to disk without memory spikes. Incorporates real-time `pypdf` extraction to handle latin-1 encoded PDF buffers reliably.
- **Binary Graph-RAG**: PDFs and other binary documents now participate fully in Graph-RAG. Branch A extracts text via `pypdf`, and Branch B consumes that extracted text for entity/relation extraction — eliminating the previous "binary files are processed via File API only" limitation.
- **Local Native Async Extraction**: Routes structured data extraction (Business Rules) to **Llama 3.2** via a local Ollama instance utilizing the **Ollama 2026 SDK** with Native Tool Calling and automated Pydantic schema conversion.
- **Dynamic Thinking Detection**: The `LLMGateway` dynamically evaluates the configured `OLLAMA_BUSINESS_MODEL` against a whitelist of thinking-capable models (Qwen 3, DeepSeek) before injecting the `think` parameter — preventing 400 errors on non-thinking models like Llama 3.2.
- **VRAM-Safe Orchestration**: A strict sequential orchestration uses a high-performance **Priority Scheduler** with **Aging** and worker-pool execution (`OLLAMA_WORKERS=2`). This replaces the global semaphore, preventing starvation of low-priority tasks while ensuring model isolation via aggressive offloading (`keep_alive=0`).
- **Transactional Consistency (C_03)**: Uses nested DB transactions/savepoints where the background task orchestrator acts as the sole boundary owner. Services never commit, preserving the constitutional atomicity.
- **Integrity Gating (C_01)**: Implements persistent validation of extracted entities. Dangling relations are no longer silently dropped; they are persisted with an `is_valid=False` flag. High rates of invalid data trigger immediate confidence downgrades (`LOW`) in extraction reports.

### 2. Context Orchestration & RAG (Phase 2)

- **Lazy Project Creation**: The database starts empty — no bootstrap or hardcoded default projects. Users are guided through an onboarding modal on first access to create their project with a mandatory **stack** declaration (`python`, `rust`, `typescript`, `generic`).
- **Stack-Aware Strategy Resolution**: Project `stack` is persisted in `config_json` and drives the `StrategyResolver` factory to select the appropriate prompt strategy at runtime. An explicit `VALID_STACKS` set ensures only recognized stacks are accepted, with `GenericStrategy` as a safe fallback.
- **Hybrid Cache Routing**: Orchestrates context via an explicit → implicit → inline fallback chain. The `GeminiClient` wrapper handles `caches.create` for explicit caching and `cached_content` parameter for inference using the official `google-genai` SDK.
- **Token-Aware Caching**: The `KnowledgeOrchestrator` counts tokens before caching — documents with ≥ 4096 tokens attempt explicit cache; below threshold, they are marked `READY_PARTIAL` for inline fallback.
- **Async Processing Pipeline (C_02)**: All Gemini SDK calls (`count_tokens`, `caches.create`, `models.generate_content`, `files.upload`) run inside `asyncio.to_thread()` to keep the event loop non-blocking.
- **pgvector Integration**: Native vector search support for long-term semantic retrieval.

### 3. Graph-RAG with LightRAG Pattern (Phase 3)

- **Knowledge Graph Extraction**: Automatically extracts semantic entities and relations using **Gemini Flash**. Relations are verified for referential integrity and stored with validity flags.
- **pgvector HNSW Index**: Entities are locally embedded using **Qwen3 (via Ollama)** and indexed via pgvector HNSW (`m=16`, `ef_construction=64`) for cosine similarity search.
- **Community Detection**: Leiden algorithm discovers thematic clusters. Community summaries are generated via Gemini Flash.
- **Circuit Breaker Health Check**: The `GraphQueryService` monitors graph health in real-time. If the percentage of invalid edges exceeds `GRAPH_INVALID_THRESHOLD` (default 0.3), the **Circuit Breaker opens**, forcing an automatic fallback to Phase 2 cache/semantic search to ensure reliable RAG output.
- **Three Query Modes**:
  - `local` — Entity-level: pgvector similarity → recursive CTE edge traversal → Pro synthesis.
  - `global` — Community-level: aggregated community summaries → Pro synthesis.
  - `hybrid` (default) — Local first → confidence gating → Global escalation → merge synthesis.
- **Graceful Degradation**: `READY_PARTIAL` status when graph extraction fails; hybrid mode falls back to Phase 2 cache routing when the graph is empty or the circuit breaker is open.

### 4. Prompt Generation Engine (Phase 3b)

- **Synthesis Engine**: Uses **Gemini 2.5 Pro** via `asyncio.to_thread` (C_02) to synthesize context and assemble structured YAML prompts for downstream LLM agents.
- **Tiered Strategy**: Classifies tasks as `SIMPLE` (entity-level context) or `COMPLEX` (community context + few-shot examples + code skeletons).
- **Stack-Driven Prompt Strategies**: The `StrategyResolver` factory selects prompt composition rules based on the project's declared stack:
  - `PrumoMetaStrategy` — Python/FastAPI conventions.
  - `RustSorobanStrategy` — Soroban/Stellar smart contract patterns.
  - `TypeScriptReactStrategy` — React/Next.js frontend conventions.
  - `GenericStrategy` — Universal fallback for unknown stacks.
- **Abstracted Storage (ADR-003)**: Fully decoupled from the file system via the `IOutputStorage` repository pattern.
  - **Local Strategy**: Safe asynchronous file I/O (C_02) with manual TTL cleaning.
  - **Database Strategy**: Persistent storage in the `generated_prompts` table for containerized environments.
  - **Hybrid (Both)**: Writes to both backends for maximum redundancy.
- **Opaque Identifiers**: Internal file paths are never exposed. Prompts are identified by UUIDs (`prompt_id`) and served via authenticated download endpoints.
- **Confidence-Aware Output**: Confidence is auto-downgraded via `model_validator` when context is degraded (e.g., graph blocking warnings).
- **REST API**:
  - `POST /prompts/generate-cursor-yaml` — Generates and persists the prompt.
  - `GET /prompts/{prompt_id}` — Retrieves the generated YAML for client-side download.

### 5. Developer Experience & Quality

- **HTMX Playground**: A lightweight testing interface at `/ui/` for rapid prototyping with document ingestion, status polling, knowledge queries, and data management (purge/reset).
- **Onboarding Modal**: When no projects exist, the UI renders a full-screen overlay guiding the user to create their first project with name, description, and stack — leveraging HTMX `json-enc` extension for seamless REST integration.
- **Data Management (Aba 4)**: Dedicated UI tab for project data lifecycle — reset graph entities or nuke all project data (documents + graph) with confirmation dialogs and automatic page reload.
- **Rigorous Standard**: 100% type-hinted (MyPy strict), linted (Ruff), and backed by a comprehensive test suite (pytest, pytest-mock).
- **Production Hardened**: Built with `tenacity` for resilient Gemini API retries and `structlog` for structured token-usage observability.
- **Dynamic Configuration**: All model identifiers are injected via `pydantic-settings` — zero hardcoded model strings. Switchable instantly via `.env`.

---

## 🚀 Tech Stack

| Layer          | Technology                                                                                |
| -------------- | ----------------------------------------------------------------------------------------- |
| **Core**       | FastAPI (Async Python 3.11+)                                                              |
| **Validation** | Pydantic v2 (Strict typing & validation)                                                  |
| **Cloud LLM**  | `google-genai` SDK — Gemini 2.5 Pro (synthesis) + Gemini 2.5 Flash (extraction/community) |
| **Local LLM**  | Ollama SDK (async) — Llama 3.2 (business rules) + Qwen3 (embeddings)                      |
| **Storage**    | SQLAlchemy 2.0 + PostgreSQL + `pgvector` (HNSW)                                           |
| **Graph**      | `igraph` + `leidenalg` (Leiden community detection)                                       |
| **Frontend**   | HTMX 1.9 + Tailwind CSS (Playground UI)                                                   |
| **Quality**    | `ruff` (linter), `mypy` (typing), `pytest` (tests)                                        |
| **Infra**      | `uv` (env), `alembic` (migrations), `tenacity` (resilience), `structlog` (observability)  |

---

## 📁 Project Structure

```
app/
├── config.py                           # Dynamic settings via pydantic-settings
├── database.py                         # AsyncSession factory + DI
├── main.py                             # FastAPI app + lifespan readiness check
├── core/
│   └── exceptions.py                   # Domain exception hierarchy
├── domain/
│   └── strategies/                     # Stack-aware prompt strategy implementations
│       ├── factory.py                  # StrategyResolver + VALID_STACKS registry
│       ├── prompt_strategy.py          # IPromptStrategy Protocol
│       ├── generic_strategy.py         # GenericStrategy (fallback)
│       ├── prumo_meta_strategy.py      # PrumoMetaStrategy (Python/FastAPI)
│       ├── rust_soroban_strategy.py    # RustSorobanStrategy (Soroban/Stellar)
│       └── typescript_react_strategy.py # TypeScriptReactStrategy (React/Next)
├── models/
│   ├── knowledge.py                    # KnowledgeDocument (File API + Cache + status)
│   ├── graph.py                        # GraphNode (Vector 1024d) + GraphEdge
│   ├── business_rule.py                # BusinessRule (extracted JSON)
│   ├── project.py                      # Project workspace (config_json with stack)
│   └── plan.py                         # Plan model
├── schemas/
│   ├── knowledge.py                    # KnowledgeAnswer (C_01 validators), AnswerCitation, QueryMode
│   ├── graph.py                        # EntityExtractionResult, NodeContext, EdgeContext
│   ├── business_rule.py                # BusinessRuleSchema (Pydantic + Ollama tool target)
│   └── prompt_generator.py             # PromptTier, PromptStrategyConfig, GeneratedPrompt (C_01)
├── infrastructure/
│   └── storage/                       # Storage adapters (Local, Database, Hybrid)
├── interfaces/
│   └── storage.py                     # IOutputStorage Protocol (ADR-003)
├── utils/
│   └── tool_converter.py              # Pydantic → Ollama Native Tool conversion
├── services/
│   ├── gemini_client.py               # GeminiClient wrapper (google-genai SDK, C_02)
│   ├── gemini.py                      # Gemini extraction with tenacity retries
│   ├── ollama_client.py               # VRAM-safe OllamaClient (Semaphore + keep_alive=0)
│   ├── llm_gateway.py                 # LLMGateway (dynamic think detection, C_01)
│   ├── knowledge_gemini.py            # Document pipeline (Branches A+B+C, binary Graph-RAG)
│   ├── knowledge_orchestrator.py      # Query routing + batch ingestion + token-aware caching
│   ├── document_processor.py          # VRAM-safe orchestrator (Extract → Embed)
│   ├── graph_extractor.py             # Entity/relation extraction + graph upsert
│   ├── graph_services.py             # Document deletion + project purge (cascade)
│   ├── embedding_service.py           # Local Qwen3 batch embedding
│   ├── community_detector.py          # Leiden algorithm + Gemini Flash summaries
│   ├── graph_query_service.py         # Local / Global / Hybrid query engines
│   ├── prompt_generator.py            # Tiered YAML prompt assembly engine
│   ├── file_classifier.py            # MIME-type gating for binary/text routing
│   ├── sanitizer.py                   # LLM JSON sanitization + PDF extraction
│   ├── business_rule.py               # Business rule persistence service
│   └── project.py                     # Project management service (stack-aware creation)
└── routers/
    ├── ingest.py                      # POST /ingest/business — multi-file uploads
    ├── knowledge.py                   # /knowledge/documents, /knowledge/query, /knowledge/purge-all
    ├── projects.py                    # POST /projects (stack validation + HX-Redirect)
    ├── prompts.py                     # POST /prompts/generate-cursor-yaml
    └── test_ui.py                     # HTMX powered UI playground + onboarding modal
```

---

## ⚙️ Getting Started

### Prerequisites

- Python 3.11+ and [uv](https://github.com/astral-sh/uv).
- PostgreSQL with `pgvector` (e.g., `pgvector/pgvector:pg16` Docker image).
- System library `libigraph-dev` (for `leidenalg`).
- Ollama running locally (port 11434) with models pulled: `llama3.2:3b`, `qwen3-embedding:0.6b`.

### Installation

1.  **Sync Environment**:

    ```bash
    uv sync
    ```

2.  **Configure Credentials**:

    ```bash
    cp .env.example .env
    ```

    Required environment variables:

    | Variable                  | Description                                             |
    | ------------------------- | ------------------------------------------------------- |
    | `GEMINI_API_KEY`          | Google AI Studio API key                                |
    | `DATABASE_URL`            | PostgreSQL connection string (async)                    |
    | `API_KEY`                 | Static API key for endpoint auth                        |
    | `GEMINI_SYNTHESIS_MODEL`  | Synthesis model (default: `gemini-2.5-pro`)             |
    | `GEMINI_FLASH_MODEL`      | Fast model (default: `gemini-2.5-flash`)                |
    | `OLLAMA_BUSINESS_MODEL`   | Local extraction model (default: `llama3.2:3b`)         |
    | `OLLAMA_EMBEDDING_MODEL`  | Local embedding model (default: `qwen3-embedding:0.6b`) |
    | `PROMPT_STORAGE_BACKEND`  | Storage strategy (`local`, `database`, `both`)          |
    | `GRAPH_INVALID_THRESHOLD` | Max invalid edge ratio (default `0.3`)                  |
    | `OLLAMA_WORKERS`          | Concurrent local workers (default `2`)                  |
    | `OLLAMA_REQUEST_TIMEOUT`  | Max wait for model scheduling (default `300`)           |

3.  **Database Migration**:

    ```bash
    uv run alembic upgrade head
    ```

4.  **Fire it up**:

    ```bash
    uv run uvicorn app.main:app --reload
    ```

    Access the interactive docs at: [http://localhost:8000/docs](http://localhost:8000/docs)

    Access the HTMX playground at: [http://localhost:8000/ui/](http://localhost:8000/ui/)

    > On first access, the playground will present an onboarding modal to create your first project.

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

## 📖 API Reference

### Project Creation

```bash
curl -X POST http://localhost:8000/projects \
  -H 'Content-Type: application/json' \
  -d '{"name": "My Project", "description": "A Soroban smart contract project", "stack": "rust"}'
```

Valid stacks: `generic`, `typescript`, `prumo`, `rust`.

### Business Rule Ingestion

```bash
curl -X POST http://localhost:8000/ingest/business \
  -H 'X-API-Key: <YOUR_KEY>' \
  -d '{"project_id": "...", "raw_text": "we need a python api with jwt auth..."}'
```

### Knowledge Query (3 modes)

```bash
# Hybrid (default) — graph + cache fallback
curl -X POST 'http://localhost:8000/knowledge/query?project_id=...&question=How+is+auth+handled?'

# Local — entity-level graph search
curl -X POST 'http://localhost:8000/knowledge/query?project_id=...&question=...&mode=local'

# Global — community-level summaries
curl -X POST 'http://localhost:8000/knowledge/query?project_id=...&question=...&mode=global'
```

### Data Management

```bash
# Purge graph entities only (documents remain, can be reprocessed)
curl -X DELETE 'http://localhost:8000/knowledge/purge-all?project_id=...'

# Nuke everything (documents + graph — irreversible)
curl -X DELETE 'http://localhost:8000/knowledge/purge-all?project_id=...&keep_documents=false'

# Delete a single document and its graph entities
curl -X DELETE 'http://localhost:8000/knowledge/documents/<document_id>'
```

### Prompt Generation

```bash
curl -X POST http://localhost:8000/prompts/generate-cursor-yaml \
  -H 'Content-Type: application/json' \
  -d '{
    "project_id": "...",
    "intent": "Implement JWT authentication middleware",
    "target_files": ["app/middleware/auth.py"],
    "include_skeletons": true
  }'
```

Returns a structured JSON with a `prompt_id`.

### Prompt Retrieval

```bash
curl -X GET 'http://localhost:8000/prompts/<prompt_id>?project_id=...' \
  -H 'X-API-Key: <YOUR_KEY>'
```

Returns the raw YAML content for the agent to use.

---

## 🌐 Language Policy

- **Code & Logic**: 100% English (Architecture, variables, logs, schemas).
- **Data Preservation**: While keys are English, the extracted content preserves the **original language** of the input (Portuguese, Spanish, etc.) to maintain domain fidelity.

---

<p align="center">
  <i>Part of the Prumo Context Orchestration Suite.</i>
</p>
