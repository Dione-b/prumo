---
trigger: always_on
---

---
description: Testes, qualidade e cobertura. Aplicar em arquivos dentro de tests/.
globs: tests/**/*.py
---

# Python Testing — Testes e Qualidade

## Framework e Plugins
- **Framework:** `pytest`
- **Plugins obrigatórios:** `pytest-cov`, `pytest-asyncio`, `pytest-mock`
- **Opcional:** `hypothesis` para testes de propriedade em lógica com muitos edge cases.

## Cobertura
- Meta mínima: **80%** para código de produção.
- Meta para lógica de domínio crítica: **100%**.

## Estrutura dos Testes
- **Padrão AAA:** Arrange / Act / Assert — separe cada fase com uma linha em branco.
- **Nomenclatura:** `test_<unidade>_<cenário>_<resultado_esperado>`
  - Ex: `test_create_user_with_duplicate_email_raises_conflict`
- **Isolamento:** Cada teste deve ser independente e idempotente. Sem dependência de ordem.
- **Fixtures:** Centralize em `conftest.py`. Use escopos (`session`, `module`, `function`) conscientemente.
- **Mocks:** Prefira injeção de dependência a monkey-patching. Use `pytest-mock` (`mocker`).
```python
def test_calculate_discount_gold_tier_returns_20_percent_off():
    # Arrange
    price = 100.0
    tier = "gold"

    # Act
    result = calculate_discount(price, tier)

    # Assert
    assert result == 80.0


def test_calculate_discount_negative_price_raises_value_error():
    # Arrange
    price = -10.0

    # Act / Assert
    with pytest.raises(ValueError, match="negativo"):
        calculate_discount(price, "gold")
```

## Checklist de Testes
- [ ] Caminho feliz coberto?
- [ ] Casos de erro e exceções testados?
- [ ] Edge cases (vazio, zero, None, máximo)?
- [ ] Testes assíncronos decorados com `@pytest.mark.asyncio`?
- [ ] Sem dados reais (PII, credenciais) nos fixtures?