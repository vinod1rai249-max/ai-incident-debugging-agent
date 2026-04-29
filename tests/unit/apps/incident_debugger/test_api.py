import json

from fastapi.testclient import TestClient

from apps.api.main import app
from apps.incident_debugger.api import get_orchestrator
from apps.incident_debugger.orchestrator import IncidentOrchestrator
from core.circuit_breaker import CircuitBreaker
from tests.helpers.mock_builder import MockLLMClientBuilder

# ---------------------------------------------------------------------------
# Canned responses for the three agents that run on simple incidents.
# VALID_PAYLOAD has no complex-pattern keywords so Planner and Critic are skipped.
# ---------------------------------------------------------------------------
_MOCK_CLASSIFIER = json.dumps(
    {
        "error_category": "NullReference",
        "key_signals": ["NoneType", "attribute access", "missing null guard"],
        "analysis_plan": "Investigate the call site where a None value is dereferenced.",
    }
)
_MOCK_ROOT_CAUSE = json.dumps(
    {
        "root_cause": "The transaction object is None when no row is found.",
        "contributing_factors": ["Missing null check before attribute access"],
        "affected_components": ["payment-service"],
    }
)
_MOCK_FIX = json.dumps(
    {
        "quick_fix": "Add a null guard before accessing charge_id.",
        "long_term_fix": "Enforce not-null contract at the transaction repository layer.",
        "validation_steps": [
            "Deploy fix and run integration tests against staging.",
            "Verify no new AttributeErrors appear in payment-service logs.",
        ],
        "rollback_plan": "Revert the fix commit and redeploy the previous image tag.",
    }
)

# ---------------------------------------------------------------------------
# Override the FastAPI dependency so tests never hit the real Anthropic API.
# A fresh MockLLMClient is created per request so responses never run dry.
# ---------------------------------------------------------------------------


async def _get_mock_orchestrator() -> IncidentOrchestrator:
    return IncidentOrchestrator(
        llm_client=MockLLMClientBuilder.simple(
            classifier=_MOCK_CLASSIFIER,
            root_cause=_MOCK_ROOT_CAUSE,
            fix=_MOCK_FIX,
        ),
        circuit_breaker=CircuitBreaker(name="test", min_calls=5),
        max_retries=2,
        base_wait_s=0.0,
    )


app.dependency_overrides[get_orchestrator] = _get_mock_orchestrator

client = TestClient(app)

VALID_PAYLOAD = {
    "error_message": "AttributeError: 'NoneType' object has no attribute 'charge_id'",
    "stack_trace": (
        "File payment.py line 84 in process_payment\n  charge_id = transaction.charge_id"
    ),
    "logs": "2026-04-28T10:12:01Z ERROR AttributeError NoneType",
    "service_name": "payment-service",
    "environment": "production",
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_analyze_returns_200() -> None:
    response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    assert response.status_code == 200


def test_analyze_response_has_required_fields() -> None:
    response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    body = response.json()
    assert "incident_id" in body
    assert "root_cause" in body
    assert "severity" in body
    assert "confidence_score" in body
    assert "quick_fix" in body
    assert "long_term_fix" in body
    assert "validation_steps" in body
    assert "rollback_plan" in body
    assert "metadata" in body


def test_analyze_response_incident_id_is_uuid() -> None:
    import uuid

    response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    body = response.json()
    parsed = uuid.UUID(body["incident_id"])
    assert str(parsed) == body["incident_id"]


def test_analyze_response_severity_is_valid_enum() -> None:
    response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    body = response.json()
    assert body["severity"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def test_analyze_response_confidence_score_in_range() -> None:
    response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    body = response.json()
    assert 0.0 <= body["confidence_score"] <= 1.0


def test_analyze_response_validation_steps_is_list() -> None:
    response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    body = response.json()
    assert isinstance(body["validation_steps"], list)
    assert len(body["validation_steps"]) >= 1


def test_analyze_response_metadata_structure() -> None:
    response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    meta = response.json()["metadata"]
    assert "total_cost_usd" in meta
    assert "total_latency_ms" in meta
    assert "models_used" in meta
    assert "agent_trace" in meta
    assert "degraded" in meta


def test_analyze_pipeline_not_degraded_on_success() -> None:
    # Orchestrator runs all 5 agents with valid mock responses → degraded=False
    response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    body = response.json()
    assert body["metadata"]["degraded"] is False


def test_analyze_mocked_response_is_degraded() -> None:
    # FixAgent receives bad JSON on every attempt → fallback used → degraded=True
    async def _get_degraded_orchestrator() -> IncidentOrchestrator:
        return IncidentOrchestrator(
            llm_client=MockLLMClientBuilder.simple(
                classifier=_MOCK_CLASSIFIER,
                root_cause=_MOCK_ROOT_CAUSE,
                fix="bad json",
            ),
            circuit_breaker=CircuitBreaker(name="test_degraded", min_calls=5),
            max_retries=2,
            base_wait_s=0.0,
        )

    app.dependency_overrides[get_orchestrator] = _get_degraded_orchestrator
    try:
        response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
        assert response.status_code == 200
        assert response.json()["metadata"]["degraded"] is True
    finally:
        app.dependency_overrides[get_orchestrator] = _get_mock_orchestrator


def test_analyze_each_call_gets_unique_incident_id() -> None:
    r1 = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    r2 = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    assert r1.json()["incident_id"] != r2.json()["incident_id"]


def test_analyze_with_optional_code_snippet() -> None:
    payload = {**VALID_PAYLOAD, "code_snippet": "def foo(): pass"}
    response = client.post("/api/v1/incidents/analyze", json=payload)
    assert response.status_code == 200


def test_analyze_without_service_name() -> None:
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "service_name"}
    response = client.post("/api/v1/incidents/analyze", json=payload)
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Validation errors (422)
# ---------------------------------------------------------------------------


def test_analyze_missing_error_message_returns_422() -> None:
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "error_message"}
    response = client.post("/api/v1/incidents/analyze", json=payload)
    assert response.status_code == 422


def test_analyze_missing_stack_trace_returns_422() -> None:
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "stack_trace"}
    response = client.post("/api/v1/incidents/analyze", json=payload)
    assert response.status_code == 422


def test_analyze_missing_logs_returns_422() -> None:
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "logs"}
    response = client.post("/api/v1/incidents/analyze", json=payload)
    assert response.status_code == 422


def test_analyze_empty_error_message_returns_422() -> None:
    payload = {**VALID_PAYLOAD, "error_message": ""}
    response = client.post("/api/v1/incidents/analyze", json=payload)
    assert response.status_code == 422


def test_analyze_empty_body_returns_422() -> None:
    response = client.post("/api/v1/incidents/analyze", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# X-Correlation-ID header propagation
# ---------------------------------------------------------------------------


def test_analyze_returns_correlation_id_header() -> None:
    response = client.post(
        "/api/v1/incidents/analyze",
        json=VALID_PAYLOAD,
        headers={"X-Correlation-ID": "test-corr-123"},
    )
    assert response.headers.get("X-Correlation-ID") == "test-corr-123"


def test_analyze_generates_correlation_id_when_not_provided() -> None:
    response = client.post("/api/v1/incidents/analyze", json=VALID_PAYLOAD)
    assert "X-Correlation-ID" in response.headers
    assert response.headers["X-Correlation-ID"] != ""
