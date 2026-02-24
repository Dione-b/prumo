---
trigger: always_on
---

---
description: Performance e otimização. Consultar ao trabalhar em código crítico de desempenho.
globs: **/*.py
---

# Python Performance — Eficiência e Otimização

## Regra de Ouro
**Meça antes de otimizar.** Use `cProfile`, `py-spy` ou `memray` para identificar gargalos reais antes de qualquer mudança.

## Boas Práticas
- **Generators:** Prefira a listas quando não precisar de acesso aleatório ou múltiplas iterações.
- **`functools.cache` / `lru_cache`:** Para memoização de funções puras e computacionalmente caras.
- **Invariantes fora de loops:** Extraia expressões que não mudam a cada iteração.
- **`collections`:** Use `defaultdict`, `Counter`, `deque` em vez de reinventar.
- **`"".join(lista)`:** Para concatenação de strings em loop. NUNCA `+=` em loop.
- **`__slots__`:** Em classes com muitas instâncias para reduzir alocação de memória.
- **Comparações de identidade:** `is` / `is not` para `None`, `True`, `False`. `==` para valores.
```python
from functools import lru_cache
from collections import Counter, defaultdict

# ✅ Generator — não carrega tudo na memória
def read_large_file(path: Path):
    with path.open() as f:
        yield from f

# ✅ lru_cache para função pura cara
@lru_cache(maxsize=128)
def compute_score(user_id: int, tier: str) -> float:
    ...

# ✅ Invariante fora do loop
prefix = get_prefix()
result = [f"{prefix}_{item}" for item in items]

# ❌ Recalcula a cada iteração
result = [f"{get_prefix()}_{item}" for item in items]
```

## Quando NÃO otimizar prematuramente
- Código executado raramente (scripts de setup, migrações).
- Código cuja legibilidade seria sacrificada sem ganho mensurável.
- Antes de ter um benchmark ou profiling que comprove o gargalo.