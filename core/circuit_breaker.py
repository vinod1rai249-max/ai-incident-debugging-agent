import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    CLOSED = auto()  # normal — calls go through
    OPEN = auto()  # failing — calls blocked
    HALF_OPEN = auto()  # recovering — one probe call allowed


@dataclass
class CircuitBreaker:
    """Tracks failure rate and opens the circuit when it exceeds a threshold.

    Wrap any external call (LLM, tool, retriever) with cb.call(fn, *args).
    """

    name: str
    failure_threshold: float = 0.5  # open when failure_rate >= this
    min_calls: int = 5  # minimum calls before rate is evaluated
    recovery_timeout: float = 30.0  # seconds before moving OPEN → HALF_OPEN

    _calls: int = field(default=0, init=False, repr=False)
    _failures: int = field(default=0, init=False, repr=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)
    _opened_at: float = field(default=0.0, init=False, repr=False)

    @property
    def failure_rate(self) -> float:
        return self._failures / self._calls if self._calls else 0.0

    @property
    def state(self) -> CircuitState:
        if (
            self._state is CircuitState.OPEN
            and time.monotonic() - self._opened_at >= self.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            logger.info("circuit_half_open", name=self.name)
        return self._state

    async def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if self.state is CircuitState.OPEN:
            raise CircuitOpenError(self.name)

        self._calls += 1
        try:
            result: Any = await fn(*args, **kwargs)
        except Exception as exc:
            self._record_failure()
            raise exc
        else:
            self._record_success()
            return result

    def _record_success(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._reset()
            logger.info("circuit_closed", name=self.name)

    def _record_failure(self) -> None:
        self._failures += 1
        if self._state is CircuitState.HALF_OPEN:
            self._trip()
            return
        if self._calls >= self.min_calls and self.failure_rate >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        logger.warning(
            "circuit_opened",
            name=self.name,
            failure_rate=round(self.failure_rate, 2),
            calls=self._calls,
        )

    def _reset(self) -> None:
        self._calls = 0
        self._failures = 0
        self._state = CircuitState.CLOSED


class CircuitOpenError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"Circuit '{name}' is OPEN — calls blocked until recovery timeout")
        self.name = name
