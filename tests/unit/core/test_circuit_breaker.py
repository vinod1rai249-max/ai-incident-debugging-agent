import pytest

from core.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


async def _ok() -> str:
    return "ok"


async def _fail() -> None:
    raise RuntimeError("boom")


@pytest.fixture()
def cb() -> CircuitBreaker:
    return CircuitBreaker(name="test", failure_threshold=0.5, min_calls=4)


@pytest.mark.asyncio
async def test_closed_on_success(cb: CircuitBreaker) -> None:
    await cb.call(_ok)
    assert cb.state is CircuitState.CLOSED


@pytest.mark.asyncio
async def test_opens_when_failure_rate_exceeds_threshold(cb: CircuitBreaker) -> None:
    for _ in range(2):
        await cb.call(_ok)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(_fail)
    assert cb.state is CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_circuit_blocks_calls(cb: CircuitBreaker) -> None:
    for _ in range(2):
        await cb.call(_ok)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(_fail)
    with pytest.raises(CircuitOpenError):
        await cb.call(_ok)


@pytest.mark.asyncio
async def test_failure_rate_calculation(cb: CircuitBreaker) -> None:
    await cb.call(_ok)
    with pytest.raises(RuntimeError):
        await cb.call(_fail)
    assert cb.failure_rate == pytest.approx(0.5)
