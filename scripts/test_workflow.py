"""Script de teste end-to-end para Prumo Lite.

Fluxo:
  1. Cria um projeto
  2. Ingere um documento de texto
  3. Aguarda processamento
  4. Executa query RAG
  5. Gera prompt YAML
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

import httpx

BASE_URL = "http://localhost:8000"
API_KEY = "prumo-dev-key"  # Ajustar conforme .env

SAMPLE_DOCUMENT = """
## Projeto Prumo Lite

### Regras de Negócio
1. O sistema deve aceitar documentos em formato texto e PDF.
2. Embeddings são gerados via Qwen3 através do Ollama local.
3. Busca vetorial usa pgvector com cosine similarity.
4. A síntese de respostas é feita pelo Gemini 2.5 Pro.
5. Prompts gerados em formato YAML para uso no Cursor IDE.

### Restrições Técnicas
- PostgreSQL 15+ com extensão pgvector
- Ollama rodando localmente na porta 11434
- FastAPI como framework web
- Pydantic v2 para validação
"""


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        # 1. Criar projeto
        print("=" * 60)
        print("[1/5] Criando projeto...")
        t0 = time.monotonic()

        resp = await client.post(
            "/projects",
            json={
                "name": f"test-project-{int(time.time())}",
                "description": "Projeto de teste do Prumo Lite",
            },
        )
        resp.raise_for_status()
        project = resp.json()
        project_id = project["id"]
        print(f"  ✓ Projeto criado: {project_id}")
        print(f"  ⏱ {time.monotonic() - t0:.2f}s\n")

        # 2. Ingerir documento
        print("[2/5] Ingerindo documento...")
        t0 = time.monotonic()

        resp = await client.post(
            "/knowledge/documents",
            json={
                "project_id": project_id,
                "title": "Regras do Prumo Lite",
                "content": SAMPLE_DOCUMENT,
                "source_type": "text/plain",
            },
        )
        resp.raise_for_status()
        ingest_result = resp.json()
        doc_id = ingest_result["document_id"]
        print(f"  ✓ Documento ingerido: {doc_id}")
        print(f"  ⏱ {time.monotonic() - t0:.2f}s\n")

        # 3. Aguardar processamento
        print("[3/5] Aguardando processamento (embedding)...")
        t0 = time.monotonic()

        for attempt in range(30):
            await asyncio.sleep(2)
            # Vamos verificar via query se já processou
            # Tentando query que irá retornar 404 se não houver docs READY
            try:
                resp = await client.post(
                    "/knowledge/query",
                    params={
                        "project_id": project_id,
                        "question": "test",
                    },
                )
                if resp.status_code == 200:
                    print(f"  ✓ Documento processado! (tentativa {attempt + 1})")
                    print(f"  ⏱ {time.monotonic() - t0:.2f}s\n")
                    break
            except Exception:
                pass
        else:
            print("  ✗ Timeout aguardando processamento")
            return

        # 4. Query RAG
        print("[4/5] Executando query RAG...")
        t0 = time.monotonic()

        resp = await client.post(
            "/knowledge/query",
            params={
                "project_id": project_id,
                "question": "Quais são as restrições técnicas do projeto?",
            },
        )
        resp.raise_for_status()
        answer = resp.json()
        print(f"  ✓ Resposta: {answer['answer'][:200]}...")
        print(f"  Confiança: {answer['confidence_level']}")
        print(f"  Citações: {len(answer.get('citations', []))}")
        print(f"  ⏱ {time.monotonic() - t0:.2f}s\n")

        # 5. Gerar prompt YAML
        print("[5/5] Gerando prompt YAML...")
        t0 = time.monotonic()

        resp = await client.post(
            "/prompts/generate-cursor-yaml",
            json={
                "project_id": project_id,
                "intent": "Implementar endpoint de upload de PDF com extração de texto",
                "target_files": ["app/routers/upload.py", "app/services/pdf.py"],
            },
        )
        resp.raise_for_status()
        prompt = resp.json()
        print(f"  ✓ Prompt gerado: {prompt['prompt_id']}")
        print(f"  Confiança: {prompt['confidence']}")
        print(f"  Strategies: {prompt['strategies_applied']}")
        print(f"  ⏱ {time.monotonic() - t0:.2f}s\n")

        # Resultado
        print("=" * 60)
        print("✓ Fluxo completo executado com sucesso!")
        print(f"  YAML preview (primeiros 300 chars):")
        print(f"  {prompt['yaml_prompt'][:300]}...")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
