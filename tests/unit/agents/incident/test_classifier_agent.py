import json

import pytest

from agents.incident.classifier_agent import ClassifierAgent
from apps.incident_debugger.models import AgentStepTrace, TriageResult
from core.circuit_breaker import CircuitBreaker, CircuitState
from core.exceptions import IncidentAnalysisError
from genai.clients.mock_client import MockLLMClient
from tests.unit.agents.incident.conftest import CLASSIFIER_JSON


def make_agent(responses: list[str]) -> ClassifierAgent:
    return ClassifierAgent(
        llm_client=MockLLMClient(responses),
        circuit_breaker=CircuitBreaker(name="test_cls", min_calls=5),
        max_retries=3,
        base_wait_s=0.0,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_classifier_returns_triage_result(incident, planner_result) -> None:
    agent = make_agent([CLASSIFIER_JSON])
    result, trace = await agent.run(incident=incident, planner=planner_result)
    assert isinstance(result, TriageResult)
    assert isinstance(trace, AgentStepTrace)


async def test_classifier_result_fields(incident, planner_result) -> None:
    agent = make_agent([CLASSIFIER_JSON])
    result, _ = await agent.run(incident=incident, planner=planner_result)
    assert result.error_category != ""
    assert len(result.key_signals) >= 1
    assert result.analysis_plan != ""


async def test_classifier_trace_agent_name(incident, planner_result) -> None:
    agent = make_agent([CLASSIFIER_JSON])
    _, trace = await agent.run(incident=incident, planner=planner_result)
    assert trace.agent_name == "ClassifierAgent"
    assert trace.status == "success"


# ---------------------------------------------------------------------------
# Schema validation failure triggers retry with schema hint
# ---------------------------------------------------------------------------


async def test_classifier_retries_on_missing_field(incident, planner_result) -> None:
    bad_json = json.dumps({"error_category": "NullReference"})  # missing key_signals, analysis_plan
    agent = make_agent([bad_json, CLASSIFIER_JSON])
    result, _ = await agent.run(incident=incident, planner=planner_result)
    assert isinstance(result, TriageResult)


async def test_classifier_raises_after_max_retries(incident, planner_result) -> None:
    agent = make_agent(["{}"] * 3)
    with pytest.raises(IncidentAnalysisError, match="ClassifierAgent"):
        await agent.run(incident=incident, planner=planner_result)


# ---------------------------------------------------------------------------
# Circuit open
# ---------------------------------------------------------------------------


async def test_classifier_raises_when_circuit_open(incident, planner_result) -> None:
    import time

    cb = CircuitBreaker(name="cls_open", min_calls=5)
    cb._state = CircuitState.OPEN
    cb._opened_at = time.monotonic()  # just opened — won't recover within the test
    agent = ClassifierAgent(
        llm_client=MockLLMClient([CLASSIFIER_JSON]),
        circuit_breaker=cb,
        max_retries=3,
        base_wait_s=0.0,
    )
    with pytest.raises(IncidentAnalysisError):
        await agent.run(incident=incident, planner=planner_result)
