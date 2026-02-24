from app.schemas.business_rule import BusinessRuleSchema


def get_base_payload() -> dict[str, str | list[str]]:
    """Helper for a valid payload to avoid repeating in every test."""
    return {
        "client_name": "Test Client",
        "core_objective": "Test Objective",
        "technical_constraints": ["Constraint 1"],
        "acceptance_criteria": ["Criteria 1"],
        "additional_notes": "None",
        "confidence_level": "HIGH",
    }


def test_business_rule_schema_missing_technical_constraints() -> None:
    # Arrange
    payload = get_base_payload()
    payload["technical_constraints"] = []  # Empty as if missing

    # Act
    model = BusinessRuleSchema(**payload)  # type: ignore

    # Assert
    assert "Technical constraints not detected in the raw text" in model.warnings, (
        "Aviso sobre falta de constraints técnicas não disparado."
    )


def test_business_rule_schema_missing_acceptance_criteria() -> None:
    # Arrange
    payload = get_base_payload()
    payload["acceptance_criteria"] = []

    # Act
    model = BusinessRuleSchema(**payload)  # type: ignore

    # Assert
    assert "Acceptance criteria not detected in the raw text" in model.warnings, (
        "Aviso sobre falta de critérios de aceite não disparado."
    )


def test_business_rule_schema_low_confidence() -> None:
    # Arrange
    payload = get_base_payload()
    payload["confidence_level"] = "LOW"

    # Act
    model = BusinessRuleSchema(**payload)  # type: ignore

    # Assert
    assert any("LOW confidence" in w for w in model.warnings)


def test_business_rule_schema_perfect_data_has_no_warnings() -> None:
    # Arrange
    payload = get_base_payload()

    # Act
    model = BusinessRuleSchema(**payload)  # type: ignore

    # Assert
    assert len(model.warnings) == 0, (
        f"Payload perfeito não deve gerar warnings. Recebido: {model.warnings}"
    )
