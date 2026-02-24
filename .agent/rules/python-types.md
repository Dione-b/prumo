---
trigger: always_on
---

---
description: Type hints, Pydantic e contratos de tipo. Aplicar em todo arquivo .py.
globs: **/*.py
---

# Python Types — Tipagem e Validação

## Regra Geral
- Todo código novo DEVE ter type hints completos (parâmetros + retorno).
- Código deve passar em `mypy --strict` ou `pyright` sem erros.

## Sintaxe Moderna
- `list[str]`, `dict[str, int]`, `tuple[int, ...]` — NUNCA `List`, `Dict`, `Tuple` do `typing`.
- `X | Y` em vez de `Union[X, Y]`.
- `X | None` em vez de `Optional[X]`.

## Ferramentas de Tipo
| Ferramenta    | Quando usar                                               |
|---------------|-----------------------------------------------------------|
| `NewType`     | IDs e primitivos com semântica de domínio                 |
| `TypeAlias`   | Aliases complexos: `JsonDict: TypeAlias = dict[str, Any]` |
| `Final`       | Constantes reais: `MAX_CONN: Final = 10`                  |
| `Protocol`    | Duck typing estrutural (prefira a ABCs)                   |
| `TypedDict`   | Dicts com estrutura conhecida sem overhead do Pydantic    |
| `TypeVar`     | Generics em funções utilitárias                           |
| `ParamSpec`   | Generics em decoradores                                   |
| `Never`       | Funções que sempre lançam exceção                         |

## Pydantic v2
- Use `BaseModel` para todos os dados externos (API, config, eventos, DB).
- Use `@field_validator` e `@model_validator` para regras de negócio na validação.
- Use `model_config = ConfigDict(frozen=True)` para Value Objects imutáveis.
- Use `SecretStr` para campos sensíveis (senhas, tokens).
- Use `pydantic-settings` (`BaseSettings`) para configurações via env vars.
- Use `@dataclass` para objetos internos simples sem validação.
```python
from pydantic import BaseModel, ConfigDict, field_validator, SecretStr

class UserCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    email: str
    password: SecretStr

    @field_validator("email")
    @classmethod
    def email_must_have_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Email inválido")
        return v.lower()
```