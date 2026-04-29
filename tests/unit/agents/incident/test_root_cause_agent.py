import pytest

from agents.incident.root_cause_agent import RootCauseAgent
from apps.incident_debugger.models import RootCauseResult
from core.circuit_breaker import CircuitBreaker
from core.exceptions import IncidentAnalysisError
from genai.clients.mock_client import MockLLMClient
from tests.unit.agents.incident.conftest import ROOT_CAUSE_JSON


def make_agent(responses: list[str]) -> RootCauseAgent:
    return RootCauseAgent(
        llm_client=MockLLMClient(responses),
        circuit_breaker=CircuitBreaker(name="test_rca", min_calls=5),
        max_retries=3,
        base_wait_s=0.0,
    )


async def test_root_cause_returns_result(incident, classifier_result) -> None:
    agent = make_agent([ROOT_CAUSE_JSON])
    result, trace = await agent.run(incident=incident, classifier=classifier_result)
    assert isinstance(result, RootCauseResult)
    assert result.root_cause != ""


async def test_root_cause_trace_fields(incident, classifier_result) -> None:
    agent = make_agent([ROOT_CAUSE_JSON])
    _, trace = await agent.run(incident=incident, classifier=classifier_result)
    assert trace.agent_name == "RootCauseAgent"
    assert trace.status == "success"
    assert trace.cost_usd >= 0.0


async def test_root_cause_contributing_factors_non_empty(incident, classifier_result) -> None:
    agent = make_agent([ROOT_CAUSE_JSON])
    result, _ = await agent.run(incident=incident, classifier=classifier_result)
    assert len(result.contributing_factors) >= 1
    assert len(result.affected_components) >= 1


async def test_root_cause_retries_on_bad_json(incident, classifier_result) -> None:
    agent = make_agent(["not-json", ROOT_CAUSE_JSON])
    result, _ = await agent.run(incident=incident, classifier=classifier_result)
    assert isinstance(result, RootCauseResult)


async def test_root_cause_raises_after_max_retries(incident, classifier_result) -> None:
    agent = make_agent(["bad"] * 3)
    with pytest.raises(IncidentAnalysisError, match="RootCauseAgent"):
        await agent.run(incident=incident, classifier=classifier_result)


# ---------------------------------------------------------------------------
# RAG context — prompt inclusion tests
# ---------------------------------------------------------------------------

_RAG_TEXT = (
    "[1] id=servicenow sev=HIGH cause=DataWeave OBX mapping failed fix=Add OBX-3 null check\n"
    "[2] id=dynatrace sev=HIGH cause=MLLP timeout on ORU delivery fix=Increase socket timeout"
)


def test_rag_context_appears_in_rendered_prompt(incident, classifier_result) -> None:
    agent = make_agent([ROOT_CAUSE_JSON])
    context = agent._build_context(
        incident=incident, classifier=classifier_result, rag_context=_RAG_TEXT
    )
    user_msg = agent.prompt.user(**context)
    assert _RAG_TEXT in user_msg


def test_rag_context_section_header_present_when_provided(incident, classifier_result) -> None:
    agent = make_agent([ROOT_CAUSE_JSON])
    context = agent._build_context(
        incident=incident, classifier=classifier_result, rag_context=_RAG_TEXT
    )
    user_msg = agent.prompt.user(**context)
    assert "Similar Past Incidents (RAG)" in user_msg
    assert "Compare each incident above" in user_msg


def test_rag_context_section_absent_when_empty(incident, classifier_result) -> None:
    agent = make_agent([ROOT_CAUSE_JSON])
    context = agent._build_context(incident=incident, classifier=classifier_result, rag_context="")
    user_msg = agent.prompt.user(**context)
    assert "Similar Past Incidents" not in user_msg
    assert "[1]" not in user_msg


async def test_root_cause_with_rag_context_succeeds(incident, classifier_result) -> None:
    agent = make_agent([ROOT_CAUSE_JSON])
    result, trace = await agent.run(
        incident=incident, classifier=classifier_result, rag_context=_RAG_TEXT
    )
    assert isinstance(result, RootCauseResult)
    assert trace.status == "success"
    assert result.root_cause != ""
