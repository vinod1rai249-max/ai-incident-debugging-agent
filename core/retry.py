from collections.abc import Callable
from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from core.exceptions import AppError
from core.logging import get_logger

logger = get_logger(__name__)


def build_retry(
    max_attempts: int = 3,
    base_wait: float = 1.0,
    max_wait: float = 10.0,
    reraise_types: tuple[type[Exception], ...] = (AppError,),
) -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=base_wait, max=max_wait),
        retry=retry_if_exception_type(reraise_types),
        before_sleep=_log_retry,
        reraise=True,
    )


def _log_retry(retry_state: Any) -> None:
    logger.warning(
        "retrying_call",
        attempt=retry_state.attempt_number,
        exception=str(retry_state.outcome.exception()),
        wait=retry_state.next_action.sleep,
    )


def with_fallback(primary: Callable[..., Any], fallback: Callable[..., Any]) -> Callable[..., Any]:
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await primary(*args, **kwargs)
        except AppError as exc:
            logger.warning("primary_failed_using_fallback", error=str(exc))
            return await fallback(*args, **kwargs)

    return wrapper
