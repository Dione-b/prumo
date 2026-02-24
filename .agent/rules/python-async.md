---
trigger: always_on
---

---
description: Concorrência, async/await e paralelismo. Aplicar em arquivos com código assíncrono.
globs: **/*.py
---

# Python Async — Concorrência e Paralelismo

## Regra Geral
- `asyncio`: use para I/O-bound (HTTP, DB, filesystem).
- NUNCA bloqueie o event loop com operações síncronas dentro de corrotinas.

## Boas Práticas
- **`asyncio.TaskGroup` (3.11+):** Prefira a `asyncio.gather` — melhor tratamento de erros e cancelamento.
- **`asyncio.to_thread`:** Para operações bloqueantes dentro de contexto async.
- **`concurrent.futures.ProcessPoolExecutor`:** Para CPU-bound real.
- **`anyio`:** Considere para bibliotecas que precisam ser agnósticas ao backend async.
- **Locks:** Use `asyncio.Lock` em contextos async, `threading.Lock` em contextos threaded. Documente seções críticas.
- **Evite variáveis globais mutáveis** compartilhadas entre tasks/threads.
```python
import asyncio

async def fetch_all(urls: list[str]) -> list[str]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(fetch(url)) for url in urls]
    return [t.result() for t in tasks]


async def run_blocking_in_thread(data: bytes) -> str:
    return await asyncio.to_thread(cpu_heavy_parse, data)
```

## Antipadrões — Proibido
```python
# ❌ Bloqueia o event loop
async def bad():
    time.sleep(5)

# ✅ Correto
async def good():
    await asyncio.sleep(5)

# ❌ gather sem tratamento de erro adequado em produção
results = await asyncio.gather(t1(), t2(), return_exceptions=True)

# ✅ TaskGroup com tratamento explícito
async with asyncio.TaskGroup() as tg:
    task1 = tg.create_task(t1())
    task2 = tg.create_task(t2())
```