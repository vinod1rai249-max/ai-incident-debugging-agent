import pytest

from agents.incident.fix_agent import FixAgent
from apps.incident_debugger.models import FixResult
from core.circuit_breaker import CircuitBreaker
from core.exceptions import IncidentAnalysisError
from genai.clients.mock_client import MockLLMClient
from tests.unit.agents.incident.conftest import FIX_JSON


def make_agent(responses: list[str]) -> FixAgent:
    return FixAgent(
        llm_client=MockLLMClient(responses),
        circuit_breaker=CircuitBreaker(name="test_fix", min_calls=5),
        max_retries=3,
        base_wait_s=0.0,
    )


async def test_fix_returns_result(incident, root_cause_result) -> None:
    agent = make_agent([FIX_JSON])
    result, trace = await agent.run(incident=incident, root_cause=root_cause_result)
    assert isinstance(result, FixResult)


async def test_fix_validation_steps_non_empty(incident, root_cause_result) -> None:
    agent = make_agent([FIX_JSON])
    result, _ = await agent.run(incident=incident, root_cause=root_cause_result)
    assert len(result.validation_steps) >= 1


async def test_fix_rollback_plan_non_empty(incident, root_cause_result) -> None:
    agent = make_agent([FIX_JSON])
    result, _ = await agent.run(incident=incident, root_cause=root_cause_result)
    assert result.rollback_plan != ""


async def test_fix_trace_agent_name(incident, root_cause_result) -> None:
    agent = make_agent([FIX_JSON])
    _, trace = await agent.run(incident=incident, root_cause=root_cause_result)
    assert trace.agent_name == "FixAgent"
    assert trace.status == "success"


async def test_fix_retries_on_bad_json(incident, root_cause_result) -> None:
    agent = make_agent(["bad", FIX_JSON])
    result, _ = await agent.run(incident=incident, root_cause=root_cause_result)
    assert isinstance(result, FixResult)


async def test_fix_raises_after_max_retries(incident, root_cause_result) -> None:
    agent = make_agent(["bad"] * 3)
    with pytest.raises(IncidentAnalysisError, match="FixAgent"):
        await agent.run(incident=incident, root_cause=root_cause_result)
