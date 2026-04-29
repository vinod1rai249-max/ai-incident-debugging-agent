import pytest

from agents.incident.planner_agent import PlannerAgent
from apps.incident_debugger.models import AgentStepTrace, PlannerResult
from core.circuit_breaker import CircuitBreaker
from core.exceptions import IncidentAnalysisError
from genai.clients.mock_client import MockLLMClient
from tests.unit.agents.incident.conftest import PLANNER_JSON


@pytest.fixture
def cb() -> CircuitBreaker:
    return CircuitBreaker(name="test_planner", min_calls=5)


def make_agent(responses: list[str], cb: CircuitBreaker) -> PlannerAgent:
    return PlannerAgent(
        llm_client=MockLLMClient(responses),
        circuit_breaker=cb,
        max_retries=3,
        base_wait_s=0.0,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_planner_returns_result_and_trace(incident, cb) -> None:
    agent = make_agent([PLANNER_JSON], cb)
    result, trace = await agent.run(incident=incident)
    assert isinstance(result, PlannerResult)
    assert isinstance(trace, AgentStepTrace)


async def test_planner_result_fields(incident, cb) -> None:
    agent = make_agent([PLANNER_JSON], cb)
    result, _ = await agent.run(incident=incident)
    assert len(result.steps) >= 1
    assert result.estimated_complexity in {"simple", "moderate", "complex"}


async def test_planner_trace_success_status(incident, cb) -> None:
    agent = make_agent([PLANNER_JSON], cb)
    _, trace = await agent.run(incident=incident)
    assert trace.status == "success"
    assert trace.agent_name == "PlannerAgent"


async def test_planner_trace_has_tokens(incident, cb) -> None:
    agent = make_agent([PLANNER_JSON], cb)
    _, trace = await agent.run(incident=incident)
    assert trace.input_tokens > 0
    assert trace.output_tokens > 0


async def test_planner_trace_has_positive_latency(incident, cb) -> None:
    agent = make_agent([PLANNER_JSON], cb)
    _, trace = await agent.run(incident=incident)
    assert trace.latency_ms >= 0.0


# ---------------------------------------------------------------------------
# Retry on bad JSON — succeeds on second attempt
# ---------------------------------------------------------------------------


async def test_planner_retries_on_bad_json(incident, cb) -> None:
    agent = make_agent(["not-valid-json", PLANNER_JSON], cb)
    result, trace = await agent.run(incident=incident)
    assert isinstance(result, PlannerResult)
    assert trace.status == "success"


# ---------------------------------------------------------------------------
# Exhausted retries raises IncidentAnalysisError
# ---------------------------------------------------------------------------


async def test_planner_raises_after_max_retries(incident, cb) -> None:
    agent = make_agent(["bad"] * 3, cb)
    with pytest.raises(IncidentAnalysisError, match="PlannerAgent"):
        await agent.run(incident=incident)


# ---------------------------------------------------------------------------
# Circuit breaker open — raises immediately without retrying
# ---------------------------------------------------------------------------


async def test_planner_raises_on_circuit_open(incident) -> None:
    import time

    from core.circuit_breaker import CircuitState

    cb = CircuitBreaker(name="tripped", failure_threshold=0.5, min_calls=5)
    cb._state = CircuitState.OPEN
    cb._opened_at = time.monotonic()  # just opened — recovery_timeout=30s won't elapse

    agent = make_agent([PLANNER_JSON], cb)
    with pytest.raises(IncidentAnalysisError):
        await agent.run(incident=incident)
