---
trigger: always_on
---

---
description: Segurança, secrets e proteção de dados. Aplicar em todo arquivo .py.
globs: **/*.py
---

# Python Security — Segurança e Proteção de Dados

## Secrets e Configuração
- **NUNCA** hardcode credenciais, tokens ou chaves no código.
- Use variáveis de ambiente + `pydantic-settings` (`BaseSettings`) ou `python-dotenv`.
- Mantenha `.env.example` no repositório. NUNCA commite `.env`.
- Versione dependências com versões fixadas (`uv lock` ou `pip-compile`).

## Validação de Entrada
- **TODA entrada externa** (API, arquivo, env var, CLI) deve passar por um schema Pydantic antes de ser usada.
- Nunca confie em dados não validados para lógica de negócio.

## Banco de Dados
- **NUNCA** interpole input do usuário em queries SQL.
- Use ORMs (SQLAlchemy, Tortoise) ou queries parametrizadas sempre.

## Serialização
- **NUNCA** use `pickle` com dados não confiáveis.
- Prefira JSON, `msgpack` ou `protobuf` para serialização de dados externos.

## Dados Sensíveis
- Use `pydantic.SecretStr` para campos de senha e token em schemas.
- Mascare dados sensíveis antes de logar.
- Nunca retorne stack traces completos para o cliente em produção.
```python
# ❌ Proibido
password = "super_secret_123"
query = f"SELECT * FROM users WHERE email = '{email}'"

# ✅ Correto
from pydantic import SecretStr
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    api_secret: SecretStr

    class Config:
        env_file = ".env"
```