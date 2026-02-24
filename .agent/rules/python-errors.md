---
trigger: always_on
---

---
description: Tratamento de erros, logging e resiliência. Aplicar em todo arquivo .py.
globs: **/*.py
---

# Python Errors — Tratamento de Erros e Logging

## Exceções
- **EAFP:** Prefira `try/except` a verificações defensivas excessivas.
- **Proibido:** `except:` bare e `except Exception:` sem intenção explícita.
- **Nunca engula erros silenciosamente.** Se ignorar, documente com comentário.
- Use `contextlib.suppress(ExpectedException)` para ignorar exceções esperadas de forma legível.

## Hierarquia de Exceções de Domínio
Crie sempre uma hierarquia própria. Nunca lance `Exception` puro.
```python
class AppError(Exception):
    """Base para todas as exceções da aplicação."""

class NotFoundError(AppError):
    """Recurso não encontrado."""

class ConflictError(AppError):
    """Violação de regra de unicidade."""

class ValidationError(AppError):
    """Dados de entrada inválidos."""
```

## Context Managers
- Use `with` para TODOS os recursos: arquivos, conexões, locks, sessões.
- Implemente `__enter__`/`__exit__` ou use `@contextlib.contextmanager`.

## Logging
- **Proibido `print()`** em código de produção.
- Use `logging` (stdlib) ou `loguru` (terceiro).
- Níveis corretos:
  - `DEBUG`: informações de desenvolvimento.
  - `INFO`: fluxo normal da aplicação.
  - `WARNING`: anomalia recuperável.
  - `ERROR` / `CRITICAL`: falha real.
- **Structured logging:** Em serviços, use JSON com campos consistentes (`request_id`, `user_id`, `duration_ms`).
- **Nunca logue dados sensíveis:** Mascare senhas, tokens e PII antes do log.
```python
import logging

logger = logging.getLogger(__name__)

def process_order(order_id: int) -> None:
    try:
        # ...
        logger.info("Pedido processado", extra={"order_id": order_id})
    except NotFoundError:
        logger.warning("Pedido não encontrado", extra={"order_id": order_id})
        raise
    except AppError:
        logger.exception("Falha ao processar pedido", extra={"order_id": order_id})
        raise
```