import pytest

from agents.incident.critic_agent import CriticAgent
from apps.incident_debugger.models import CriticResult, SeverityLevel
from core.circuit_breaker import CircuitBreaker
from core.exceptions import IncidentAnalysisError
from genai.clients.mock_client import MockLLMClient
from tests.unit.agents.incident.conftest import CRITIC_JSON


def make_agent(responses: list[str]) -> CriticAgent:
    return CriticAgent(
        llm_client=MockLLMClient(responses),
        circuit_breaker=CircuitBreaker(name="test_critic", min_calls=5),
        max_retries=3,
        base_wait_s=0.0,
    )


async def test_critic_returns_result(incident, root_cause_result, fix_result) -> None:
    agent = make_agent([CRITIC_JSON])
    result, trace = await agent.run(incident=incident, root_cause=root_cause_result, fix=fix_result)
    assert isinstance(result, CriticResult)


async def test_critic_severity_is_valid_enum(incident, root_cause_result, fix_result) -> None:
    agent = make_agent([CRITIC_JSON])
    result, _ = await agent.run(incident=incident, root_cause=root_cause_result, fix=fix_result)
    assert result.severity in SeverityLevel


async def test_critic_confidence_in_range(incident, root_cause_result, fix_result) -> None:
    agent = make_agent([CRITIC_JSON])
    result, _ = await agent.run(incident=incident, root_cause=root_cause_result, fix=fix_result)
    assert 0.0 <= result.confidence_score <= 1.0


async def test_critic_trace_agent_name(incident, root_cause_result, fix_result) -> None:
    agent = make_agent([CRITIC_JSON])
    _, trace = await agent.run(incident=incident, root_cause=root_cause_result, fix=fix_result)
    assert trace.agent_name == "CriticAgent"
    assert trace.status == "success"


async def test_critic_retries_on_bad_json(incident, root_cause_result, fix_result) -> None:
    agent = make_agent(["bad", CRITIC_JSON])
    result, _ = await agent.run(incident=incident, root_cause=root_cause_result, fix=fix_result)
    assert isinstance(result, CriticResult)


async def test_critic_raises_after_max_retries(incident, root_cause_result, fix_result) -> None:
    agent = make_agent(["bad"] * 3)
    with pytest.raises(IncidentAnalysisError, match="CriticAgent"):
        await agent.run(incident=incident, root_cause=root_cause_result, fix=fix_result)
