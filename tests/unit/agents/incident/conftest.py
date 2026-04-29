"""Shared fixtures for incident agent tests."""

import json

import pytest

from apps.incident_debugger.models import (
    CriticResult,
    FixResult,
    IncidentInput,
    PlannerResult,
    RootCauseResult,
    SeverityLevel,
    TriageResult,
)
from core.circuit_breaker import CircuitBreaker
from genai.clients.mock_client import MockLLMClient


@pytest.fixture
def incident() -> IncidentInput:
    return IncidentInput(
        error_message="AttributeError: 'NoneType' object has no attribute 'charge_id'",
        stack_trace="File payment.py line 84\n  charge_id = transaction.charge_id",
        logs="2026-04-28 ERROR NoneType attribute access",
        service_name="payment-service",
        environment="production",
    )


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    return CircuitBreaker(name="test_cb", failure_threshold=0.5, min_calls=5)


def make_client(*responses: str) -> MockLLMClient:
    return MockLLMClient(list(responses))


PLANNER_JSON = json.dumps(
    {
        "steps": ["Identify error type", "Analyse stack trace"],
        "priority_signals": ["NoneType", "attribute access"],
        "estimated_complexity": "moderate",
    }
)

CLASSIFIER_JSON = json.dumps(
    {
        "error_category": "NullReference",
        "key_signals": ["NoneType", "missing null guard"],
        "analysis_plan": "Investigate null dereference at the call site.",
    }
)

ROOT_CAUSE_JSON = json.dumps(
    {
        "root_cause": (
            "transaction is None when DB returns no rows;"
            " caller dereferences without null guard."
        ),
        "contributing_factors": ["missing null check"],
        "affected_components": ["payment-service"],
    }
)

FIX_JSON = json.dumps(
    {
        "quick_fix": "Add null guard before accessing transaction.charge_id.",
        "long_term_fix": "Enforce not-null return contract on db.get_transaction().",
        "validation_steps": ["Deploy fix", "Verify no new errors for 10 minutes"],
        "rollback_plan": "Revert commit and redeploy previous image.",
    }
)

CRITIC_JSON = json.dumps(
    {
        "severity": "HIGH",
        "confidence_score": 0.85,
        "review_notes": "Specific root cause, actionable fix, complete validation.",
    }
)


@pytest.fixture
def planner_result() -> PlannerResult:
    return PlannerResult(
        steps=["Identify error type", "Analyse stack trace"],
        priority_signals=["NoneType", "attribute access"],
        estimated_complexity="moderate",
    )


@pytest.fixture
def classifier_result() -> TriageResult:
    return TriageResult(
        error_category="NullReference",
        key_signals=["NoneType", "missing null guard"],
        analysis_plan="Investigate null dereference at the call site.",
    )


@pytest.fixture
def root_cause_result() -> RootCauseResult:
    return RootCauseResult(
        root_cause="transaction is None; caller dereferences without null guard.",
        contributing_factors=["missing null check"],
        affected_components=["payment-service"],
    )


@pytest.fixture
def fix_result() -> FixResult:
    return FixResult(
        quick_fix="Add null guard before accessing transaction.charge_id.",
        long_term_fix="Enforce not-null return contract on db.get_transaction().",
        validation_steps=["Deploy fix", "Verify no new errors for 10 minutes"],
        rollback_plan="Revert commit and redeploy previous image.",
    )


@pytest.fixture
def critic_result() -> CriticResult:
    return CriticResult(
        severity=SeverityLevel.HIGH,
        confidence_score=0.85,
        review_notes="Good analysis.",
    )
