"""OllamaClient — centralized local model access."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog
from ollama import AsyncClient

from app.config import settings

logger = structlog.get_logger()

# Prioridades Base (menor = maior prioridade)
PRIORITY_1 = 1.0  # RAG queries
PRIORITY_2 = 2.0  # Chat / Tool Calling / Business Rules
PRIORITY_3 = 3.0  # Embeddings

# Configuração Aging
AGING_INTERVAL_SECONDS = 30.0
AGING_DECREMENT = 0.5


@dataclass(order=True)
class QueueItem:
    """Item da fila de prioridade do Ollama."""
    effective_priority: float
    timestamp: float
    # future can't be ordered so we skip it
    future: asyncio.Future[Any] = field(compare=False)
    operation_type: Literal["chat", "generate", "embed"] = field(compare=False)
    kwargs: dict[str, Any] = field(compare=False)


class _OllamaScheduler:
    """Implementa PriorityQueue com Aging para gerenciar acessos locais ao cluster."""

    def __init__(self, workers: int = settings.ollama_workers) -> None:
        self.queue: asyncio.PriorityQueue[QueueItem] = asyncio.PriorityQueue()
        self.workers = workers
        self._tasks: list[asyncio.Task[None]] = []
        self._aging_task: asyncio.Task[None] | None = None
        self._client = AsyncClient(host=settings.ollama_base_url)

    async def start(self) -> None:
        if not self._tasks:
            for i in range(self.workers):
                task = asyncio.create_task(self._worker(f"ollama_worker_{i}"))
                self._tasks.append(task)
            self._aging_task = asyncio.create_task(self._aging_loop())

    async def _aging_loop(self) -> None:
        """Diminui a prioridade de tarefas antigas para evitar starvation."""
        while True:
            await asyncio.sleep(AGING_INTERVAL_SECONDS)
            now = time.monotonic()
            
            # Recria a fila temporária consumindo a antiga
            temp_queue: list[QueueItem] = []
            while not self.queue.empty():
                item = self.queue.get_nowait()
                if not item.future.done():
                    wait_time = now - item.timestamp
                    intervals = wait_time // AGING_INTERVAL_SECONDS
                    if intervals > 0:
                        new_priority = max(1.0, item.effective_priority - AGING_DECREMENT * intervals)
                        item.effective_priority = new_priority
                    temp_queue.append(item)

            for item in temp_queue:
                self.queue.put_nowait(item)

    async def _worker(self, name: str) -> None:
        """Consome itens da fila e roda o modelo garantindo VRAM management."""
        while True:
            item = await self.queue.get()

            if item.future.done():
                self.queue.task_done()
                continue

            start_time = time.monotonic()
            logger.debug(
                "ollama_worker_start",
                worker=name,
                op=item.operation_type,
                eff_prio=item.effective_priority,
                wait_time=start_time - item.timestamp
            )

            try:
                # OLLAMA_KEEP_ALIVE=0 ativado por definição no payload
                if item.operation_type == "chat":
                    res = await self._client.chat(**item.kwargs)
                elif item.operation_type == "generate":
                    res = await self._client.generate(**item.kwargs)
                elif item.operation_type == "embed":
                    res = await self._client.embed(**item.kwargs)
                else:
                    raise ValueError(f"Unknown operation: {item.operation_type}")

                if not item.future.done():
                    item.future.set_result(res)
            except Exception as e:
                logger.exception("ollama_worker_operation_failed", error=str(e), op=item.operation_type)
                if not item.future.done():
                    item.future.set_exception(e)
            finally:
                self.queue.task_done()

    async def enqueue(
        self,
        base_priority: float,
        op: Literal["chat", "generate", "embed"],
        **kwargs: Any
    ) -> Any:
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        item = QueueItem(
            effective_priority=base_priority,
            timestamp=time.monotonic(),
            future=future,
            operation_type=op,
            kwargs=kwargs,
        )
        
        await self.queue.put(item)
        
        try:
            return await asyncio.wait_for(future, timeout=settings.ollama_request_timeout)
        except asyncio.TimeoutError as exc:
            logger.warning("ollama_operation_timeout", op=op, timeout=settings.ollama_request_timeout)
            future.cancel()
            raise exc

# Singleton local para gerenciar o scheduler
_scheduler = _OllamaScheduler()


class OllamaClient:
    """Centralizes local model access using PriorityQueue with Aging."""

    def __init__(self) -> None:
        self._scheduler = _scheduler

    async def __aenter__(self):
        await self._scheduler.start()
        return self
        
    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        think: bool = True,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Sends a prioritary chat request."""
        # Garante inicialização
        await self._scheduler.start()

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        final_options: dict[str, Any] = {
            "keep_alive": settings.ollama_keep_alive,
        }
        if options is not None:
            final_options.update(options)
        kwargs["options"] = final_options

        if tools is not None:
            kwargs["tools"] = tools
        if think:
            kwargs["think"] = True

        return await self._scheduler.enqueue(PRIORITY_2, "chat", **kwargs)

    async def generate(self, model: str, prompt: str, format: str = "") -> Any:
        """Sends a generate request with strict VRAM offload."""
        await self._scheduler.start()

        kwargs: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "options": {"keep_alive": settings.ollama_keep_alive},
        }
        if format:
            kwargs["format"] = format
            
        return await self._scheduler.enqueue(PRIORITY_1, "generate", **kwargs)

    async def embed(self, model: str, input_texts: list[str]) -> Any:
        """Sends an embedding request with strict VRAM offload."""
        await self._scheduler.start()

        kwargs: dict[str, Any] = {
            "model": model,
            "input": input_texts,
            "options": {"keep_alive": settings.ollama_keep_alive},
        }

        return await self._scheduler.enqueue(PRIORITY_3, "embed", **kwargs)
