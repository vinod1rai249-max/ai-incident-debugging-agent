from typing import Any

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from core.exceptions import ValidationError
from core.logging import get_logger

logger = get_logger(__name__)


def validate_output(result: Any, schema: type[BaseModel], *, context: str = "") -> BaseModel:
    """Parse and validate an agent/LLM result against a Pydantic schema.

    Raises ValidationError (our typed exception) so callers can catch it
    uniformly alongside LLMError, ToolError, etc.
    """
    if result is None:
        raise ValidationError(f"Output is None{_ctx(context)}")

    if isinstance(result, str) and not result.strip():
        raise ValidationError(f"Output is empty string{_ctx(context)}")

    if isinstance(result, dict) and "error" in result:
        raise ValidationError(f"Output contains error key: {result['error']}{_ctx(context)}")

    try:
        if isinstance(result, schema):
            validated = result
        elif isinstance(result, dict):
            validated = schema.model_validate(result)
        else:
            validated = schema.model_validate(result)
    except PydanticValidationError as exc:
        field_errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
        raise ValidationError(
            f"Output failed schema validation{_ctx(context)}: {'; '.join(field_errors)}"
        ) from exc

    logger.debug("output_validated", schema=schema.__name__, context=context or "unset")
    return validated


def _ctx(context: str) -> str:
    return f" [{context}]" if context else ""
