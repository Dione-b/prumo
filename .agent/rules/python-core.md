---
trigger: always_on
---

---
description: Estilo, formatação e sintaxe Python moderna (3.10+). Aplicar em todo arquivo .py.
globs: **/*.py
---

# Python Core — Estilo e Sintaxe Moderna

## Mindset
- Legibilidade > Cleverness. Código é lido mais vezes do que escrito.
- "Pythonico": use os idiomas da linguagem. Não escreva Java em Python.
- Meça antes de otimizar.

## Formatação
- Siga PEP 8 rigorosamente.
- Formatador: `Ruff` (preferido) ou `Black`. Line length: 88 chars.
- Linter: `Ruff` com regras `E`, `W`, `F`, `I`, `N`, `UP` ativas.

## Imports
- Ordem obrigatória: Standard Lib → Third Party → Local.
- Sem imports circulares. Reestruture o código se necessário.
- Use `from __future__ import annotations` no topo para avaliação lazy de tipos.

## Naming
| Contexto          | Estilo                | Exemplo                        |
|-------------------|-----------------------|--------------------------------|
| Variáveis/Funções | `snake_case`          | `user_name`, `get_user`        |
| Classes           | `PascalCase`          | `UserService`                  |
| Constantes        | `UPPER_SNAKE_CASE`    | `MAX_RETRIES`                  |
| Privados          | `_leading_underscore` | `_internal_cache`              |
| Type Aliases      | `PascalCase`          | `UserId = NewType("UserId", int)` |
| Dunder            | `__double__`          | Apenas para protocolo Python   |

## Sintaxe Moderna (3.10+)
- **Pathlib:** SEMPRE `pathlib.Path`. NUNCA `os.path` ou strings cruas para caminhos.
- **F-strings:** SEMPRE para interpolação. Proibido `.format()` e `%s`.
  - Para f-strings longas, extraia variáveis intermediárias.
- **Match/Case:** Use para despacho com mais de 3 ramos sobre o mesmo valor.
- **Walrus (`:=`):** Só quando reduz repetição real (ex: `while chunk := f.read(8192)`). Proibido para "parecer esperto".
- **`enumerate` / `zip`:** Sempre prefira a índice manual em loops.
- **`any()` / `all()`:** Use com generator expressions para curto-circuito.
- **`"".join(lista)`:** Para concatenação de strings em loop. Nunca `+=` em loop.

## Docstrings
- Formato: **Google Style** para todas as funções e classes públicas.
- Documente o *porquê*, não o *o quê* óbvio.
- Obrigatório em: funções não triviais, métodos públicos, módulos.
```python
def calculate_discount(price: float, user_tier: str) -> float:
    """Calcula o desconto com base no tier do usuário.

    Args:
        price: Preço original em reais. Deve ser >= 0.
        user_tier: Tier do usuário ('gold', 'silver', 'bronze').

    Returns:
        Preço final após desconto.

    Raises:
        ValueError: Se `price` for negativo ou `user_tier` inválido.

    Example:
        >>> calculate_discount(100.0, "gold")
        80.0
    """
```