import pytest

from apps.incident_debugger.models import IncidentInput, IncidentReport, SeverityLevel
from apps.incident_debugger.orchestrator import IncidentOrchestrator
from core.circuit_breaker import CircuitBreaker
from genai.clients.mock_client import MockLLMClient
from tests.helpers.mock_builder import MockLLMClientBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_orchestrator(
    client: MockLLMClient,
    cb: CircuitBreaker | None = None,
) -> IncidentOrchestrator:
    return IncidentOrchestrator(
        llm_client=client,
        circuit_breaker=cb or CircuitBreaker(name="test_orch", min_calls=5),
        max_retries=2,
        base_wait_s=0.0,
    )


@pytest.fixture
def incident() -> IncidentInput:
    return IncidentInput(
        error_message="AttributeError: 'NoneType' object has no attribute 'charge_id'",
        stack_trace="File payment.py line 84\n  charge_id = transaction.charge_id",
        logs="2026-04-28 ERROR NoneType",
        service_name="payment-service",
        environment="production",
    )


@pytest.fixture
def complex_incident() -> IncidentInput:
    """An incident that triggers the full 5-agent pipeline (matches high-complexity patterns)."""
    return IncidentInput(
        error_message="CRITICAL: deadlock detected in payment-service — transaction lock timeout",
        stack_trace="File payment.py line 84\n  charge_id = transaction.charge_id",
        logs="2026-04-28 ERROR deadlock detected",
        service_name="payment-service",
        environment="production",
    )


# ---------------------------------------------------------------------------
# Happy path — simple incident (Planner + Critic skipped)
# ---------------------------------------------------------------------------


async def test_full_pipeline_returns_incident_report(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert isinstance(report, IncidentReport)


async def test_full_pipeline_incident_id_is_uuid(incident) -> None:
    import uuid

    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    uuid.UUID(report.incident_id)  # raises if not valid UUID


async def test_full_pipeline_root_cause_non_empty(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert report.root_cause != ""
    assert "[MOCK]" not in report.root_cause


async def test_full_pipeline_severity_valid(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert report.severity in SeverityLevel


async def test_full_pipeline_confidence_in_range(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert 0.0 <= report.confidence_score <= 1.0


async def test_full_pipeline_validation_steps_non_empty(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert len(report.validation_steps) >= 1


async def test_full_pipeline_rollback_plan_non_empty(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert report.rollback_plan != ""


async def test_full_pipeline_not_degraded(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert report.metadata.degraded is False


async def test_full_pipeline_models_used_non_empty(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert len(report.metadata.models_used) >= 1


async def test_full_pipeline_cost_is_non_negative(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert report.metadata.total_cost_usd >= 0.0


async def test_full_pipeline_latency_is_positive(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(incident)
    assert report.metadata.total_latency_ms >= 0.0


# ---------------------------------------------------------------------------
# Happy path — complex incident (all 5 agents)
# ---------------------------------------------------------------------------


async def test_full_pipeline_agent_trace_has_5_entries(complex_incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.complex())
    report = await orch.run(complex_incident)
    assert len(report.metadata.agent_trace) == 5


# ---------------------------------------------------------------------------
# Degraded path — planner fails (NON-BLOCKING, complex incident only)
# ---------------------------------------------------------------------------


async def test_planner_failure_pipeline_continues(complex_incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.complex(planner=["bad", "bad"]))
    report = await orch.run(complex_incident)
    assert isinstance(report, IncidentReport)
    assert report.metadata.degraded is True


async def test_planner_failure_trace_shows_error(complex_incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.complex(planner=["bad", "bad"]))
    report = await orch.run(complex_incident)
    planner_trace = next(t for t in report.metadata.agent_trace if t.agent_name == "PlannerAgent")
    assert planner_trace.status == "error"


# ---------------------------------------------------------------------------
# Degraded path — fix fails (NON-BLOCKING) → fallback fix used
# ---------------------------------------------------------------------------


async def test_fix_failure_uses_fallback(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple(fix=["bad", "bad"]))
    report = await orch.run(incident)
    assert report.metadata.degraded is True
    assert "runbook" in report.quick_fix.lower() or report.quick_fix != ""


# ---------------------------------------------------------------------------
# Degraded path — critic fails (NON-BLOCKING) → defaults to HIGH / 0.3
# ---------------------------------------------------------------------------


async def test_critic_failure_defaults_to_high(complex_incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.complex(critic=["bad", "bad"]))
    report = await orch.run(complex_incident)
    assert report.metadata.degraded is True
    assert report.severity == SeverityLevel.HIGH
    assert report.confidence_score == 0.3


# ---------------------------------------------------------------------------
# Blocking failure — classifier fails → DEGRADED report with confidence=0
# ---------------------------------------------------------------------------


async def test_classifier_blocking_failure_returns_degraded(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple(classifier=["bad", "bad"]))
    report = await orch.run(incident)
    assert report.metadata.degraded is True
    assert report.confidence_score == 0.0
    assert report.severity == SeverityLevel.HIGH


# ---------------------------------------------------------------------------
# Cost limit exceeded — pipeline aborts mid-run
# ---------------------------------------------------------------------------


async def test_cost_limit_returns_degraded_report(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    orch.MAX_COST_USD = 0.0  # trip immediately on first agent success
    report = await orch.run(incident)
    assert report.metadata.degraded is True


# ---------------------------------------------------------------------------
# Each call produces a unique incident_id
# ---------------------------------------------------------------------------


async def test_two_runs_produce_different_ids(incident) -> None:
    r1 = await make_orchestrator(MockLLMClientBuilder.simple()).run(incident)
    r2 = await make_orchestrator(MockLLMClientBuilder.simple()).run(incident)
    assert r1.incident_id != r2.incident_id


# ---------------------------------------------------------------------------
# Dev-only force flags — only active when environment in {"dev", "local"}
# ---------------------------------------------------------------------------


@pytest.fixture
def dev_incident() -> IncidentInput:
    """Incident with environment='dev' so force flags are honoured."""
    return IncidentInput(
        error_message="AttributeError: 'NoneType' object has no attribute 'charge_id'",
        stack_trace="File payment.py line 84\n  charge_id = transaction.charge_id",
        logs="2026-04-28 ERROR NoneType",
        service_name="payment-service",
        environment="dev",
    )


async def test_force_degraded_returns_degraded_report(dev_incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    forced = dev_incident.model_copy(update={"force_degraded": True})
    report = await orch.run(forced)
    assert report.metadata.degraded is True


async def test_force_degraded_root_cause_contains_sentinel(dev_incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    forced = dev_incident.model_copy(update={"force_degraded": True})
    report = await orch.run(forced)
    assert "force_degraded" in report.root_cause


async def test_force_degraded_uses_fallback_confidence(dev_incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    forced = dev_incident.model_copy(update={"force_degraded": True})
    report = await orch.run(forced)
    assert report.confidence_score == pytest.approx(0.3)


async def test_force_blocking_failure_returns_zero_confidence(dev_incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    forced = dev_incident.model_copy(update={"force_blocking_failure": True})
    report = await orch.run(forced)
    assert report.confidence_score == 0.0
    assert report.metadata.degraded is True


async def test_force_blocking_failure_takes_priority_over_force_degraded(
    dev_incident,
) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    forced = dev_incident.model_copy(
        update={"force_blocking_failure": True, "force_degraded": True}
    )
    report = await orch.run(forced)
    assert report.confidence_score == 0.0


async def test_force_flags_bypass_cache(dev_incident) -> None:
    """Each force-flag call must return a fresh report — never a cached one."""
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    forced = dev_incident.model_copy(update={"force_degraded": True})
    r1 = await orch.run(forced)
    r2 = await orch.run(forced)
    assert r1.incident_id != r2.incident_id


# -- Ignored when environment is not dev/local --------------------------------


async def test_force_degraded_ignored_for_production_incidents(incident) -> None:
    """incident fixture has environment='production' — flag must be silently ignored."""
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    forced = incident.model_copy(update={"force_degraded": True})
    report = await orch.run(forced)
    assert report.metadata.degraded is False


async def test_force_blocking_failure_ignored_for_production_incidents(incident) -> None:
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    forced = incident.model_copy(update={"force_blocking_failure": True})
    report = await orch.run(forced)
    assert report.confidence_score > 0.0
    assert report.metadata.degraded is False


async def test_force_degraded_ignored_for_staging_incidents() -> None:
    staging = IncidentInput(
        error_message="err",
        stack_trace="trace",
        logs="log",
        environment="staging",
        force_degraded=True,
    )
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(staging)
    assert report.metadata.degraded is False


async def test_force_flags_active_for_local_environment() -> None:
    local_incident = IncidentInput(
        error_message="err",
        stack_trace="trace",
        logs="log",
        environment="local",
        force_degraded=True,
    )
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    report = await orch.run(local_incident)
    assert report.metadata.degraded is True


# -- Server-side defence: production server ignores flags even for dev env ----


async def test_force_flags_ignored_on_production_server(
    dev_incident, monkeypatch
) -> None:
    from unittest.mock import MagicMock

    import apps.incident_debugger.orchestrator as orch_mod

    monkeypatch.setattr(orch_mod, "settings", MagicMock(is_production=True))
    orch = make_orchestrator(MockLLMClientBuilder.simple())
    forced = dev_incident.model_copy(update={"force_degraded": True})
    report = await orch.run(forced)
    assert report.metadata.degraded is False
