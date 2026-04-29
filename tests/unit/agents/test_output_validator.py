import pytest
from pydantic import BaseModel

from agents.validation.output_validator import validate_output
from core.exceptions import ValidationError


class _Answer(BaseModel):
    text: str
    confidence: float


def test_valid_dict_passes() -> None:
    result = validate_output({"text": "hello", "confidence": 0.9}, _Answer)
    assert isinstance(result, _Answer)
    assert result.text == "hello"


def test_valid_model_instance_passes() -> None:
    instance = _Answer(text="ok", confidence=1.0)
    assert validate_output(instance, _Answer) is instance


def test_none_raises() -> None:
    with pytest.raises(ValidationError, match="None"):
        validate_output(None, _Answer)


def test_empty_string_raises() -> None:
    with pytest.raises(ValidationError, match="empty string"):
        validate_output("   ", _Answer)


def test_dict_with_error_key_raises() -> None:
    with pytest.raises(ValidationError, match="error key"):
        validate_output({"error": "something broke"}, _Answer)


def test_missing_field_raises() -> None:
    with pytest.raises(ValidationError, match="schema validation"):
        validate_output({"text": "hi"}, _Answer)  # missing confidence


def test_wrong_type_raises() -> None:
    with pytest.raises(ValidationError):
        validate_output({"text": "hi", "confidence": "not-a-float"}, _Answer)


def test_context_included_in_message() -> None:
    with pytest.raises(ValidationError, match="rag_step"):
        validate_output(None, _Answer, context="rag_step")
