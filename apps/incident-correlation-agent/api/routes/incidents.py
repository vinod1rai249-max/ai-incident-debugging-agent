from agent.tools.correlation_tools import correlate
from agent.tools.dynatrace_tools import fetch_problems
from agent.tools.servicenow_tools import fetch_incident_by_number, fetch_incidents
from fastapi import APIRouter, HTTPException, Query
from models.correlation import CorrelationResult
from models.incident import ServiceNowIncident

from core.logging_config import get_logger
from core.metrics import high_priority_incidents, incident_count

router = APIRouter(prefix="/incidents", tags=["incidents"])
logger = get_logger(__name__)


@router.get("/", response_model=list[ServiceNowIncident])
async def list_incidents(
    state: str | None = Query(default="1,2,3", description="Comma-separated SN state codes"),
    limit: int = Query(default=50, le=200),
):
    state_codes = state.split(",")
    query = "^OR".join(f"state={s.strip()}" for s in state_codes)

    try:
        incidents = await fetch_incidents(state_query=query, limit=limit)
        _update_prometheus_counts(incidents)
        return incidents
    except Exception as exc:
        logger.error("fetch_incidents_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"ServiceNow unreachable: {exc}") from exc


@router.get("/{number}", response_model=ServiceNowIncident)
async def get_incident(number: str):
    incident = await fetch_incident_by_number(number)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {number} not found")
    return incident


@router.get("/correlated/all", response_model=list[CorrelationResult])
async def get_correlated_incidents(
    state: str | None = Query(default="1,2,3"),
    limit: int = Query(default=50, le=200),
):
    state_codes = state.split(",")
    query = "^OR".join(f"state={s.strip()}" for s in state_codes)

    try:
        incidents, problems = await _fetch_both(query, limit)
    except Exception as exc:
        logger.error("correlation_fetch_failed", error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    results = correlate(incidents, problems)
    _update_prometheus_counts(incidents)
    return results


async def _fetch_both(query: str, limit: int):
    import asyncio

    return await asyncio.gather(
        fetch_incidents(state_query=query, limit=limit),
        fetch_problems(),
    )


def _update_prometheus_counts(incidents: list[ServiceNowIncident]) -> None:
    counts: dict = {}
    hp_count = 0

    for inc in incidents:
        key = (inc.priority, inc.state)
        counts[key] = counts.get(key, 0) + 1
        if inc.is_high_priority:
            hp_count += 1

    for (priority, state), count in counts.items():
        incident_count.labels(priority=priority, state=state).set(count)

    high_priority_incidents.set(hp_count)
