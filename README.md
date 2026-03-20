# Prumo Lite

Automatiza a criação de prompts de implementação a partir de documentos e regras de negócio — reduzindo de 2 horas para minutos.

## O que faz

1. **Ingestão de documentos** (texto e PDF) — extrai regras de negócio via Llama 3.2 e gera embeddings via Qwen3
2. **RAG simples** — busca vetorial (pgvector) para consultar a base de conhecimento do projeto
3. **Geração de prompt YAML** — combina regras, contexto relevante e template estruturado para agentes do Cursor IDE

## Stack

| Componente | Tecnologia |
|---|---|
| **API** | FastAPI + Pydantic v2 |
| **Banco** | PostgreSQL 15+ com pgvector |
| **Embeddings** | Qwen3 via Ollama (local) |
| **Extração** | Llama 3.2 via Ollama (local) |
| **Síntese** | Gemini 2.5 Pro (cloud) |
| **ORM** | SQLAlchemy 2.0 (async) |

## Pré-requisitos

- Python 3.11+
- PostgreSQL 15+ com extensão `pgvector`
- Ollama rodando localmente
- Chave de API do Gemini

## Setup

```bash
# 1. Instalar dependências
uv sync

# 2. Configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas credenciais

# 3. Executar migrações
uv run alembic upgrade head

# 4. Baixar modelos Ollama
ollama pull llama3.2:3b
ollama pull qwen3-embedding:0.6b

# 5. Rodar
uv run uvicorn app.main:app --reload
```

## API Endpoints

### Projects
- `POST /projects` — Cria um projeto
- `GET /projects` — Lista projetos

### Ingestion
- `POST /ingest/business` — Ingere texto e extrai regras de negócio

### Knowledge Base
- `POST /knowledge/documents` — Ingere documento para RAG
- `POST /knowledge/query` — Consulta via busca vetorial + síntese Gemini
- `DELETE /knowledge/documents/{id}` — Remove documento
- `DELETE /knowledge/purge-all` — Limpa todos os documentos do projeto

### Prompts
- `POST /prompts/generate-cursor-yaml` — Gera prompt YAML estruturado
- `GET /prompts/{id}` — Baixa o prompt gerado

## Teste rápido

```bash
uv run python scripts/test_workflow.py
```

## Licença

AGPL-3.0 — Veja [LICENSE](LICENSE).
