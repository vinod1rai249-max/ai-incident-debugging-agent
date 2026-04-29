import pytest
from pydantic import ValidationError as PydanticValidationError

from apps.incident_debugger.models import (
    AgentEnvelope,
    AgentStepTrace,
    AnalysisMetadata,
    CriticResult,
    FixResult,
    IncidentInput,
    IncidentReport,
    RootCauseResult,
    SeverityLevel,
    TriageResult,
)

# ---------------------------------------------------------------------------
# IncidentInput
# ---------------------------------------------------------------------------


def test_incident_input_valid() -> None:
    inp = IncidentInput(
        error_message="NullPointerException",
        stack_trace="at com.example.Main.run(Main.java:10)",
        logs="ERROR 2026-04-28 service crashed",
    )
    assert inp.environment == "production"
    assert inp.code_snippet is None
    assert inp.service_name is None


def test_incident_input_with_optional_fields() -> None:
    inp = IncidentInput(
        error_message="KeyError: 'DB_URL'",
        stack_trace="File config.py line 5",
        logs="CRITICAL startup failed",
        code_snippet="url = os.environ['DB_URL']",
        service_name="auth-service",
        environment="staging",
    )
    assert inp.service_name == "auth-service"
    assert inp.environment == "staging"
    assert inp.code_snippet is not None


def test_incident_input_empty_error_message_raises() -> None:
    with pytest.raises(PydanticValidationError):
        IncidentInput(error_message="", stack_trace="trace", logs="logs")


def test_incident_input_empty_stack_trace_raises() -> None:
    with pytest.raises(PydanticValidationError):
        IncidentInput(error_message="error", stack_trace="", logs="logs")


def test_incident_input_empty_logs_raises() -> None:
    with pytest.raises(PydanticValidationError):
        IncidentInput(error_message="error", stack_trace="trace", logs="")


# ---------------------------------------------------------------------------
# SeverityLevel
# ---------------------------------------------------------------------------


def test_severity_level_values() -> None:
    assert SeverityLevel.CRITICAL == "CRITICAL"
    assert SeverityLevel.HIGH == "HIGH"
    assert SeverityLevel.MEDIUM == "MEDIUM"
    assert SeverityLevel.LOW == "LOW"


def test_severity_level_invalid_raises() -> None:
    with pytest.raises(PydanticValidationError):
        CriticResult(severity="UNKNOWN", confidence_score=0.5, review_notes="ok")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TriageResult
# ---------------------------------------------------------------------------


def test_triage_result_valid() -> None:
    t = TriageResult(
        error_category="NullReference",
        key_signals=["NoneType", "attribute access"],
        analysis_plan="Analyse stack trace for null dereference pattern.",
    )
    assert len(t.key_signals) == 2


# ---------------------------------------------------------------------------
# RootCauseResult
# ---------------------------------------------------------------------------


def test_root_cause_result_valid() -> None:
    r = RootCauseResult(
        root_cause="Transaction object is None when DB returns no rows.",
        contributing_factors=["missing null check", "no default value"],
        affected_components=["payment-service", "DB layer"],
    )
    assert r.root_cause != ""


# ---------------------------------------------------------------------------
# FixResult
# ---------------------------------------------------------------------------


def test_fix_result_valid() -> None:
    f = FixResult(
        quick_fix="Add null guard before accessing charge_id.",
        long_term_fix="Enforce not-null contract at the repository layer.",
        validation_steps=["Deploy fix", "Verify no new AttributeErrors in logs"],
        rollback_plan="Revert commit abc123 and redeploy.",
    )
    assert len(f.validation_steps) >= 1


def test_fix_result_empty_validation_steps_raises() -> None:
    with pytest.raises(PydanticValidationError):
        FixResult(
            quick_fix="Fix it",
            validation_steps=[],
            rollback_plan="Rollback.",
        )


def test_fix_result_empty_rollback_plan_is_valid() -> None:
    f = FixResult(quick_fix="Fix it", validation_steps=["step 1"])
    assert f.rollback_plan == ""


def test_fix_result_short_rollback_plan_is_valid_but_warns(caplog) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        f = FixResult(
            quick_fix="Fix it",
            validation_steps=["step 1"],
            rollback_plan="revert",  # 6 chars — below threshold, non-empty
        )
    assert f.rollback_plan == "revert"
    assert any("rollback_plan_too_short" in r.message for r in caplog.records)


def test_fix_result_adequate_rollback_plan_does_not_warn(caplog) -> None:
    import logging

    with caplog.at_level(logging.WARNING):
        FixResult(
            quick_fix="Fix it",
            validation_steps=["step 1"],
            rollback_plan="Revert commit and redeploy previous image.",
        )
    assert not any("rollback_plan_too_short" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# CriticResult
# ---------------------------------------------------------------------------


def test_critic_result_valid() -> None:
    c = CriticResult(severity=SeverityLevel.HIGH, confidence_score=0.85, review_notes="Good.")
    assert c.confidence_score == 0.85


def test_critic_result_confidence_above_1_raises() -> None:
    with pytest.raises(PydanticValidationError):
        CriticResult(severity=SeverityLevel.HIGH, confidence_score=1.1, review_notes="x")


def test_critic_result_confidence_below_0_raises() -> None:
    with pytest.raises(PydanticValidationError):
        CriticResult(severity=SeverityLevel.HIGH, confidence_score=-0.1, review_notes="x")


# ---------------------------------------------------------------------------
# AgentStepTrace
# ---------------------------------------------------------------------------


def test_agent_step_trace_valid() -> None:
    trace = AgentStepTrace(
        agent_name="TriageAgent",
        model_id="claude-haiku-4-5-20251001",
        status="success",
        latency_ms=142.5,
        input_tokens=512,
        output_tokens=210,
        cost_usd=0.0003,
    )
    assert trace.error is None


def test_agent_step_trace_with_error() -> None:
    trace = AgentStepTrace(
        agent_name="RootCauseAgent",
        model_id="claude-opus-4-7",
        status="error",
        latency_ms=0.0,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        error="LLMError: rate_limit",
    )
    assert trace.error == "LLMError: rate_limit"


def test_agent_step_trace_negative_latency_raises() -> None:
    with pytest.raises(PydanticValidationError):
        AgentStepTrace(
            agent_name="TriageAgent",
            model_id="claude-haiku-4-5-20251001",
            status="success",
            latency_ms=-1.0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
        )


# ---------------------------------------------------------------------------
# AnalysisMetadata
# ---------------------------------------------------------------------------


def test_analysis_metadata_valid() -> None:
    meta = AnalysisMetadata(
        total_cost_usd=0.043,
        total_latency_ms=3200.0,
        models_used=["claude-opus-4-7", "claude-sonnet-4-6"],
        agent_trace=[],
    )
    assert meta.degraded is False


def test_analysis_metadata_degraded_flag() -> None:
    meta = AnalysisMetadata(
        total_cost_usd=0.0,
        total_latency_ms=0.0,
        models_used=[],
        agent_trace=[],
        degraded=True,
    )
    assert meta.degraded is True


# ---------------------------------------------------------------------------
# IncidentReport
# ---------------------------------------------------------------------------


def test_incident_report_auto_generates_id() -> None:
    report = IncidentReport(
        root_cause="DB pool exhausted.",
        severity=SeverityLevel.CRITICAL,
        confidence_score=0.9,
        quick_fix="Increase pool size.",
        long_term_fix="Tune pool config and add connection-limit alerting.",
        validation_steps=["Check connection count"],
        rollback_plan="Revert pool config.",
        metadata=AnalysisMetadata(
            total_cost_usd=0.05,
            total_latency_ms=5000.0,
            models_used=["claude-opus-4-7"],
            agent_trace=[],
        ),
    )
    assert report.incident_id != ""
    assert len(report.incident_id) == 36  # UUID format


def test_incident_report_two_instances_have_different_ids() -> None:
    meta = AnalysisMetadata(
        total_cost_usd=0.0, total_latency_ms=0.0, models_used=[], agent_trace=[]
    )
    kwargs = dict(
        root_cause="x",
        severity=SeverityLevel.LOW,
        confidence_score=0.5,
        quick_fix="y",
        long_term_fix="z",
        validation_steps=["z"],
        rollback_plan="r",
        metadata=meta,
    )
    r1 = IncidentReport(**kwargs)  # type: ignore[arg-type]
    r2 = IncidentReport(**kwargs)  # type: ignore[arg-type]
    assert r1.incident_id != r2.incident_id


def test_incident_report_confidence_bounds() -> None:
    meta = AnalysisMetadata(
        total_cost_usd=0.0, total_latency_ms=0.0, models_used=[], agent_trace=[]
    )
    with pytest.raises(PydanticValidationError):
        IncidentReport(
            root_cause="x",
            severity=SeverityLevel.LOW,
            confidence_score=1.5,
            quick_fix="y",
            long_term_fix="z",
            validation_steps=["z"],
            rollback_plan="r",
            metadata=meta,
        )


# ---------------------------------------------------------------------------
# AgentEnvelope
# ---------------------------------------------------------------------------


def test_agent_envelope_valid() -> None:
    env = AgentEnvelope(
        task="incident-abc",
        status="success",
        artifacts={"root_cause": "DB pool exhausted"},
        next_agent="FixSuggestionAgent",
    )
    assert env.errors == []
    assert env.cost_usd == 0.0


def test_agent_envelope_invalid_status_raises() -> None:
    with pytest.raises(PydanticValidationError):
        AgentEnvelope(
            task="x",
            status="unknown",  # type: ignore[arg-type]
            artifacts={},
            next_agent="done",
        )
