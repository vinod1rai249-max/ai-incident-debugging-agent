"""Evaluation harness — runs all 10 labeled fixture cases through the pipeline.

Unit-speed variant: uses MockLLMClient with canned responses to assert structural
correctness (non-empty fields, types, confidence in range, no crashes).

E2E variant (pytest.mark.e2e): uses real AnthropicClient when ANTHROPIC_API_KEY
is set; asserts semantic quality (keywords, severity proximity, min confidence).
Skipped automatically when no API key is configured.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from apps.incident_debugger.models import IncidentInput, IncidentReport, SeverityLevel
from apps.incident_debugger.orchestrator import IncidentOrchestrator
from core.circuit_breaker import CircuitBreaker
from core.config import settings
from tests.helpers.mock_builder import MockLLMClientBuilder

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIXTURES_PATH = pathlib.Path(__file__).parent.parent / "fixtures" / "incident_cases.json"

_SEVERITY_ORDER = [
    SeverityLevel.LOW,
    SeverityLevel.MEDIUM,
    SeverityLevel.HIGH,
    SeverityLevel.CRITICAL,
]

# Canned per-case mock responses — structurally valid, semantically lightweight.
# Each tuple: (planner, classifier, root_cause, fix, critic)
_MOCK_PLANNER = json.dumps(
    {
        "steps": ["Identify error type", "Analyse stack trace", "Determine root cause"],
        "priority_signals": ["error_message", "stack_trace"],
        "estimated_complexity": "moderate",
    }
)
_MOCK_CLASSIFIER = json.dumps(
    {
        "error_category": "ApplicationError",
        "key_signals": ["error detected", "service impacted"],
        "analysis_plan": "Investigate the root cause of the error.",
    }
)
_MOCK_ROOT_CAUSE = json.dumps(
    {
        "root_cause": "The application encountered an unhandled error condition.",
        "contributing_factors": ["missing validation", "insufficient error handling"],
        "affected_components": ["application-service"],
    }
)
_MOCK_FIX = json.dumps(
    {
        "quick_fix": "Add proper error handling and input validation to prevent the error.",
        "long_term_fix": "Refactor the affected module to enforce input contracts at boundaries.",
        "validation_steps": [
            "Deploy fix to staging and run integration tests.",
            "Monitor error rate for 10 minutes after deployment.",
        ],
        "rollback_plan": "Revert to previous deployment if error rate rises above 1%.",
    }
)
_MOCK_CRITIC = json.dumps(
    {
        "severity": "HIGH",
        "confidence_score": 0.75,
        "review_notes": "Root cause identified, fix is actionable, rollback defined.",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_cases() -> list[dict]:
    return json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))


def _make_orchestrator_mock() -> IncidentOrchestrator:
    # Use complex() to cover both simple and complex fixture cases with a single factory.
    # For simple incidents (planner/critic skipped) the planner response is consumed by
    # Classifier's first failed attempt before it succeeds on retry — an acceptable
    # implicit retry in this integration harness where per-case complexity is not known.
    return IncidentOrchestrator(
        llm_client=MockLLMClientBuilder.complex(
            planner=_MOCK_PLANNER,
            classifier=_MOCK_CLASSIFIER,
            root_cause=_MOCK_ROOT_CAUSE,
            fix=_MOCK_FIX,
            critic=_MOCK_CRITIC,
        ),
        circuit_breaker=CircuitBreaker(name="eval_harness", min_calls=5),
        max_retries=2,
        base_wait_s=0.0,
    )


def _severity_distance(actual: SeverityLevel, expected_str: str) -> int:
    """Returns how many levels apart the severities are (0 = exact match)."""
    expected = SeverityLevel(expected_str)
    return abs(_SEVERITY_ORDER.index(actual) - _SEVERITY_ORDER.index(expected))


def _assert_structural(report: IncidentReport, case_id: str) -> list[str]:
    """Structural assertions valid for both mock and real runs. Returns failure messages."""
    failures: list[str] = []
    if not report.root_cause:
        failures.append(f"{case_id}: root_cause is empty")
    if report.severity not in SeverityLevel:
        failures.append(f"{case_id}: invalid severity {report.severity}")
    if not (0.0 <= report.confidence_score <= 1.0):
        failures.append(f"{case_id}: confidence {report.confidence_score} out of range")
    if not report.quick_fix:
        failures.append(f"{case_id}: quick_fix is empty")
    if len(report.validation_steps) < 1:
        failures.append(f"{case_id}: validation_steps is empty")
    if len(report.rollback_plan) < 10:
        failures.append(f"{case_id}: rollback_plan too short")
    return failures


def _assert_semantic(
    report: IncidentReport,
    expected: dict,
    case_id: str,
) -> list[str]:
    """Semantic assertions for real LLM runs."""
    failures: list[str] = []
    if _severity_distance(report.severity, expected["severity"]) > 1:
        failures.append(
            f"{case_id}: severity {report.severity} more than 1 level from {expected['severity']}"
        )
    if report.confidence_score < expected["min_confidence"]:
        failures.append(
            f"{case_id}: confidence {report.confidence_score:.2f} < {expected['min_confidence']}"
        )
    root_cause_lower = report.root_cause.lower()
    matched = any(kw.lower() in root_cause_lower for kw in expected["root_cause_keywords"])
    if not matched:
        failures.append(f"{case_id}: none of {expected['root_cause_keywords']} found in root_cause")
    if len(report.validation_steps) < 2:
        failures.append(
            f"{case_id}: expected ≥2 validation_steps, got {len(report.validation_steps)}"
        )
    if len(report.rollback_plan) < 20:
        failures.append(f"{case_id}: rollback_plan too short (<20 chars)")
    if report.metadata.total_cost_usd > settings.incident_max_cost_usd:
        failures.append(
            f"{case_id}: cost ${report.metadata.total_cost_usd:.4f}"
            f" exceeds ceiling ${settings.incident_max_cost_usd}"
        )
    return failures


# ---------------------------------------------------------------------------
# Unit-speed structural tests (always run — no API key needed)
# ---------------------------------------------------------------------------


async def test_harness_fixture_file_has_10_cases() -> None:
    cases = _load_cases()
    assert len(cases) == 10


async def test_harness_all_cases_have_required_keys() -> None:
    for case in _load_cases():
        assert "id" in case
        assert "input" in case
        assert "expected" in case
        inp = case["input"]
        assert "error_message" in inp
        assert "stack_trace" in inp
        assert "logs" in inp
        exp = case["expected"]
        assert "severity" in exp
        assert "root_cause_keywords" in exp
        assert "min_confidence" in exp


async def test_harness_mock_pipeline_all_cases_pass_structural() -> None:
    """All 10 cases must produce a structurally valid IncidentReport via mock LLM."""
    cases = _load_cases()
    all_failures: list[str] = []
    passed = 0

    for case in cases:
        inp = case["input"]
        incident = IncidentInput(
            error_message=inp["error_message"],
            stack_trace=inp["stack_trace"],
            logs=inp["logs"],
            code_snippet=inp.get("code_snippet"),
            service_name=inp.get("service_name"),
            environment=inp.get("environment", "production"),
        )
        orchestrator = _make_orchestrator_mock()
        report = await orchestrator.run(incident)
        failures = _assert_structural(report, case["id"])
        if not failures:
            passed += 1
        else:
            all_failures.extend(failures)

    assert passed == 10, "Structural failures:\n" + "\n".join(all_failures)


async def test_harness_mock_pipeline_no_report_is_http500() -> None:
    """Pipeline must never raise — always return a report (possibly degraded)."""
    cases = _load_cases()
    for case in cases:
        inp = case["input"]
        incident = IncidentInput(
            error_message=inp["error_message"],
            stack_trace=inp["stack_trace"],
            logs=inp["logs"],
        )
        orchestrator = _make_orchestrator_mock()
        report = await orchestrator.run(incident)
        assert isinstance(report, IncidentReport), f"{case['id']}: expected IncidentReport"


async def test_harness_mock_pipeline_reports_have_unique_incident_ids() -> None:
    cases = _load_cases()
    ids: set[str] = set()
    for case in cases:
        inp = case["input"]
        incident = IncidentInput(
            error_message=inp["error_message"],
            stack_trace=inp["stack_trace"],
            logs=inp["logs"],
        )
        orchestrator = _make_orchestrator_mock()
        report = await orchestrator.run(incident)
        assert report.incident_id not in ids, f"Duplicate incident_id for {case['id']}"
        ids.add(report.incident_id)


async def test_harness_mock_pipeline_metadata_structure() -> None:
    cases = _load_cases()
    for case in cases[:3]:  # spot-check first 3
        inp = case["input"]
        incident = IncidentInput(
            error_message=inp["error_message"],
            stack_trace=inp["stack_trace"],
            logs=inp["logs"],
        )
        orchestrator = _make_orchestrator_mock()
        report = await orchestrator.run(incident)
        meta = report.metadata
        assert meta.total_latency_ms >= 0.0
        assert meta.total_cost_usd >= 0.0
        assert len(meta.agent_trace) == 5
        assert len(meta.models_used) >= 1


# ---------------------------------------------------------------------------
# E2E semantic tests (requires ANTHROPIC_API_KEY — skipped otherwise)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.skipif(
    not (settings.anthropic_api_key and settings.anthropic_api_key.startswith("sk-ant-")),
    reason="Valid ANTHROPIC_API_KEY not configured — skipping real LLM evaluation",
)
async def test_harness_real_llm_semantic_pass_rate() -> None:
    """Run all 10 cases with real LLM; ≥8/10 must pass all semantic assertions."""
    from genai.clients.anthropic_client import AnthropicClient

    cases = _load_cases()
    passed = 0
    all_failures: list[str] = []

    for i, case in enumerate(cases):
        inp = case["input"]
        incident = IncidentInput(
            error_message=inp["error_message"],
            stack_trace=inp["stack_trace"],
            logs=inp["logs"],
            code_snippet=inp.get("code_snippet"),
            service_name=inp.get("service_name"),
            environment=inp.get("environment", "production"),
        )
        orchestrator = IncidentOrchestrator(
            llm_client=AnthropicClient(model=settings.model_name),
            max_retries=2,
            base_wait_s=1.0,
        )
        report = await orchestrator.run(incident)

        # After the first case, check for credit exhaustion so we skip early
        # rather than burning retries on all 10 cases just to hit a billing error.
        if i == 0 and report.metadata.degraded:
            credit_issue = "credit balance" in report.root_cause.lower() or any(
                t.error and "credit balance" in t.error.lower() for t in report.metadata.agent_trace
            )
            if credit_issue:
                pytest.skip("Anthropic API credit balance exhausted — add credits and re-run")

        struct_failures = _assert_structural(report, case["id"])
        sem_failures = _assert_semantic(report, case["expected"], case["id"])
        case_failures = struct_failures + sem_failures
        if not case_failures:
            passed += 1
        else:
            all_failures.extend(case_failures)

    assert passed >= 8, (
        f"Only {passed}/10 cases passed (threshold: 8/10).\nFailures:\n" + "\n".join(all_failures)
    )
