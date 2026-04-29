from datetime import UTC, datetime

import pytest
from models.incident import ServiceNowIncident
from models.trace import DynatraceProblem


@pytest.fixture
def sample_incident():
    return ServiceNowIncident(
        sys_id="abc123",
        number="INC0010001",
        short_description="Payment service 500 errors",
        description="High error rate on payment-api since 10:00 UTC",
        state="1",
        priority="1 - Critical",
        urgency="1",
        impact="1",
        category="Software",
        cmdb_ci="payment-api",
        opened_at=datetime(2024, 1, 15, 10, 5, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_problem():
    return DynatraceProblem(
        problem_id="P-12345",
        display_id="P-12345",
        title="High failure rate on payment-api",
        status="OPEN",
        severity_level="ERROR",
        impact_level="SERVICE",
        start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        end_time=None,
        impacted_entities=[
            {"entityId": {"id": "SERVICE-ABC", "type": "SERVICE"}, "name": "payment-api"}
        ],
    )


@pytest.fixture
def unrelated_problem():
    return DynatraceProblem(
        problem_id="P-99999",
        display_id="P-99999",
        title="Database latency on auth-service",
        status="OPEN",
        severity_level="PERFORMANCE",
        impact_level="SERVICE",
        start_time=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        impacted_entities=[
            {"entityId": {"id": "SERVICE-ZZZ", "type": "SERVICE"}, "name": "auth-service"}
        ],
    )
