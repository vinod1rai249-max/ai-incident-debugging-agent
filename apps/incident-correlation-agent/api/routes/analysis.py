from agent.correlation_agent import CorrelationAgent
from agent.tools.correlation_tools import correlate
from agent.tools.dynatrace_tools import fetch_problems, fetch_service_metrics
from agent.tools.servicenow_tools import fetch_incident_by_number, fetch_incidents
from fastapi import APIRouter, Body, HTTPException
from models.correlation import CorrelationAnalysis

from core.logging_config import get_logger
from core.metrics import error_rate as error_rate_gauge

router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = get_logger(__name__)

_agent = CorrelationAgent()


@router.post("/incident/{number}", response_model=CorrelationAnalysis)
async def analyze_incident(number: str):
    """Fetch a single incident, correlate with Dynatrace, run AI analysis."""
    incident = await fetch_incident_by_number(number)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {number} not found")

    problems = await fetch_problems()
    correlated = correlate([incident], problems)
    if not correlated:
        raise HTTPException(status_code=500, detail="Correlation produced no result")

    result = correlated[0]

    # Enrich with service metrics if matched problems have entities
    service_ids: list[str] = []
    for p in result.matched_problems:
        for entity in p.impacted_entities:
            eid = entity.get("entityId", {}).get("id", "")
            if eid and eid not in service_ids:
                service_ids.append(eid)

    for eid in service_ids[:3]:  # cap at 3 to avoid rate limits
        try:
            metric = await fetch_service_metrics(eid)
            if metric:
                result.service_metrics.append(metric)
                if metric.error_rate is not None:
                    error_rate_gauge.labels(service_name=metric.service_name).set(metric.error_rate)
        except Exception as exc:
            logger.warning("metric_fetch_failed", entity=eid, error=str(exc))

    analysis = await _agent.analyze(result)
    return CorrelationAnalysis(correlation=result, analysis=analysis)


@router.post("/batch", response_model=list[CorrelationAnalysis])
async def analyze_batch(
    state: str = Body(default="1,2", embed=True),
    limit: int = Body(default=10, embed=True),
):
    """Analyze all open incidents in batch (up to limit)."""
    import asyncio

    state_codes = state.split(",")
    query = "^OR".join(f"state={s.strip()}" for s in state_codes)

    incidents, problems = await asyncio.gather(
        fetch_incidents(state_query=query, limit=limit),
        fetch_problems(),
    )

    correlations = correlate(incidents, problems)

    analyses: list[CorrelationAnalysis] = []
    for corr in correlations:
        analysis = await _agent.analyze(corr)
        analyses.append(CorrelationAnalysis(correlation=corr, analysis=analysis))

    return analyses
