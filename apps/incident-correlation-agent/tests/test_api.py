from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from api.main import app
from httpx import ASGITransport, AsyncClient
from models.incident import ServiceNowIncident
from models.trace import DynatraceProblem


@pytest.fixture
def mock_incident():
    return ServiceNowIncident(
        sys_id="abc",
        number="INC0001",
        short_description="Test incident",
        state="1",
        priority="2 - High",
        urgency="2",
        impact="2",
        cmdb_ci="my-service",
        opened_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def mock_problem():
    return DynatraceProblem(
        problem_id="P-001",
        display_id="P-001",
        title="High failure rate on my-service",
        status="OPEN",
        severity_level="ERROR",
        impact_level="SERVICE",
        start_time=datetime(2024, 1, 1, 11, 50, 0, tzinfo=UTC),
        impacted_entities=[
            {"entityId": {"id": "SVC-001", "type": "SERVICE"}, "name": "my-service"}
        ],
    )


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_incidents(mock_incident):
    with patch("api.routes.incidents.fetch_incidents", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [mock_incident]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/incidents/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["number"] == "INC0001"


@pytest.mark.asyncio
async def test_metrics_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert b"servicenow_incident_count" in resp.content


@pytest.mark.asyncio
async def test_incident_not_found():
    with patch("api.routes.incidents.fetch_incident_by_number", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/incidents/INC9999")
    assert resp.status_code == 404
