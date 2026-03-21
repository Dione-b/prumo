"""Script de teste end-to-end para Prumo Lite - Cookbook Generator.

Fluxo:
  1. Cria um projeto
  2. Ingere um documento texto contendo um tutorial técnico (Stellar)
  3. Aguarda processamento via pipeline background
  4. Lista os Cookbooks extraídos via requisição GET
"""

from __future__ import annotations

import asyncio
import time
from uuid import UUID

import httpx
from pydantic import BaseModel


BASE_URL = "http://localhost:8000"

SAMPLE_DOCUMENT = """
## Como integrar a wallet Freighter no seu DApp Soroban

A Freighter é a wallet de extensão de browser recomendada para a rede Stellar.
Abaixo mostramos como solicitar a conexão na aplicação web e pedir a chave pública.

### Pré-requisitos
- Node.js 18+ instalado
- Extensão Freighter no navegador
- Pacote `@stellar/freighter-api` instalado via npm ou yarn

### Passos
1. No seu arquivo `App.tsx`, importe o pacote e crie a função de conectar.
2. Chame `setAllowed()` caso queira pedir permissão para assinar transações.
3. Chame `getPublicKey()` para carregar a conta do usuário conectado.
4. Salve no estado da aplicação.

### Exemplo de Código
```tsx
import { isAllowed, setAllowed, getPublicKey } from "@stellar/freighter-api";

async function connectWallet() {
  if (await isAllowed()) {
    const pk = await getPublicKey();
    console.log("Conectado com:", pk);
  } else {
    await setAllowed();
    const pk = await getPublicKey();
    console.log("Conectado na 1ª vez:", pk);
  }
}
```

Se ocorrer erro de conexão certifique-se de que o Freighter está logado.
Para mais informações consulte `https://docs.freighter.app`.
"""


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        # 1. Criar projeto
        print("=" * 60)
        print("[1/4] Criando projeto...")
        t0 = time.monotonic()

        resp = await client.post(
            "/projects",
            json={
                "name": f"freighter-integration-{int(time.time())}",
                "description": "Exemplo de Integração Freighter",
            },
        )
        resp.raise_for_status()
        project = resp.json()
        project_id = project["id"]
        print(f"  ✓ Projeto criado: {project_id}")
        print(f"  ⏱ {time.monotonic() - t0:.2f}s\n")

        # 2. Ingerir documento
        print("[2/4] Ingerindo documento (Newsletter da Stellar)...")
        t0 = time.monotonic()

        resp = await client.post(
            "/knowledge/documents",
            json={
                "project_id": project_id,
                "title": "Documentação Oficial Freighter",
                "content": SAMPLE_DOCUMENT,
                "source_type": "text/plain",
            },
        )
        resp.raise_for_status()
        ingest_result = resp.json()
        doc_id = ingest_result["document_id"]
        print(f"  ✓ Documento ingerido na fila: {doc_id}")
        print(f"  ⏱ {time.monotonic() - t0:.2f}s\n")

        # 3. Aguardar processamento
        print("[3/4] Aguardando processamento da extração (Gemini)...")
        t0 = time.monotonic()

        for attempt in range(15):
            await asyncio.sleep(5)
            # Vamos verificar via GET na rota de cookbooks se apareceu algo
            try:
                resp = await client.get("/cookbooks")
                if resp.status_code == 200:
                    data = resp.json()
                    if len(data) > 0:
                        print(f"  ✓ Receitas de Cookbook processadas! (tentativa {attempt + 1})")
                        print(f"  ⏱ {time.monotonic() - t0:.2f}s\n")
                        break
            except Exception as e:
                print("Error ao bater /cookbooks:", e)
        else:
            print("  ✗ Timeout aguardando as receitas ficarem prontas (pode estar demorando na API Gemini)")
            return

        # 4. Listar e exibir as receitas encontradas
        print("[4/4] Listando Cookbooks Extraídos...")
        resp = await client.get("/cookbooks")
        recipes = resp.json()
        
        print(f"Total de receitas: {len(recipes)}\n")
        for i, r in enumerate(recipes[:3]):
            print(f"--- Receita #{i+1} ---")
            print(f" Título     : {r.get('title')}")
            print(f" Descrição  : {r.get('description')}")
            print(f" Domínio    : {r.get('domain')}")
            print(f" Snippets   : {len(r.get('code_snippets') or [])}")
            print(f" Referências: {len(r.get('references') or [])}")
            print()

        print("=" * 60)
        print("✓ Fluxo completo de Gerador de Cookbook executado com sucesso!")


if __name__ == "__main__":
    asyncio.run(main())
