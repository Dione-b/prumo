---
trigger: always_on
---

---
description: Estrutura de projeto, organização de módulos e arquitetura. Consultar ao criar novos módulos ou features.
globs: src/**/*.py
---

# Python Structure — Arquitetura e Organização

## Estrutura de Diretórios
```
project/
├── src/
│   └── my_package/
│       ├── __init__.py
│       ├── core/          # Configurações, exceções base, constantes
│       ├── domain/        # Entidades, Value Objects, regras de negócio puras
│       ├── services/      # Casos de uso, orquestração de lógica
│       ├── models/        # Pydantic schemas, ORM models
│       ├── repositories/  # Abstração de acesso a dados (interfaces via Protocol)
│       ├── utils/         # Funções auxiliares puras e stateless
│       └── api/           # Rotas, handlers, controllers
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── pyproject.toml
├── .env.example
└── README.md
```

## Princípios de Dependência
- **Dependências apontam para dentro:** `api` → `services` → `domain`. Nunca o contrário.
- **`domain/` é puro:** Sem imports de frameworks externos. Testável de forma isolada.
- **`repositories/` define `Protocol`s** — implementações ficam na infraestrutura.
- **`utils/` é stateless:** Funções puras sem efeitos colaterais.

## `pyproject.toml` como Fonte Única de Verdade
Centralize configurações de todas as ferramentas:
```toml
[tool.ruff]
line-length = 88
select = ["E", "W", "F", "I", "N", "UP"]

[tool.mypy]
strict = true
python_version = "3.11"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```