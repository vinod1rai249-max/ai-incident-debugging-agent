from datetime import UTC, datetime

import httpx
from models.trace import DynatraceProblem, ServiceMetric

from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)


def _dt_headers(api_token: str) -> dict:
    return {
        "Authorization": f"Api-Token {api_token}",
        "Accept": "application/json",
    }


async def fetch_problems(status: str = "OPEN") -> list[DynatraceProblem]:
    settings = get_settings()
    url = f"{settings.dynatrace_url}/api/v2/problems"
    params = {
        "problemSelector": f"status({status})",
        "from": settings.dynatrace_problems_timeframe,
        "fields": "+impactedEntities,+rootCauseEntity,+affectedCounts",
        "pageSize": 50,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url, params=params, headers=_dt_headers(settings.dynatrace_api_token)
        )
        resp.raise_for_status()
        data = resp.json()

    problems = []
    for p in data.get("problems", []):
        try:
            problems.append(
                DynatraceProblem(
                    problem_id=p["problemId"],
                    display_id=p.get("displayId", ""),
                    title=p.get("title", ""),
                    status=p.get("status", ""),
                    severity_level=p.get("severityLevel", ""),
                    impact_level=p.get("impactLevel", ""),
                    start_time=p["startTime"],
                    end_time=p.get("endTime"),
                    impacted_entities=p.get("impactedEntities", []),
                    root_cause_entity=p.get("rootCauseEntity"),
                    affected_counts=p.get("affectedCounts", {}),
                )
            )
        except Exception as exc:
            logger.warning("problem_parse_error", problem_id=p.get("problemId"), error=str(exc))

    logger.info("dt_problems_fetched", count=len(problems))
    return problems


async def fetch_service_metrics(service_entity_id: str) -> ServiceMetric | None:
    """Fetch error rate + response time for a Dynatrace service entity."""
    settings = get_settings()
    url = f"{settings.dynatrace_url}/api/v2/metrics/query"

    selector = (
        f"builtin:service.errors.server.rate:filter(eq(dt.entity.service,{service_entity_id})):avg,"
        f"builtin:service.response.time:filter(eq(dt.entity.service,{service_entity_id})):avg,"
        f"builtin:service.requestCount.server:filter(eq(dt.entity.service,{service_entity_id})):sum"
    )
    params = {
        "metricSelector": selector,
        "from": "now-1h",
        "resolution": "1h",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url, params=params, headers=_dt_headers(settings.dynatrace_api_token)
        )
        resp.raise_for_status()
        data = resp.json()

    series_list = data.get("result", [])

    error_rate = None
    response_time = None
    request_count = None

    for series in series_list:
        metric_id = series.get("metricId", "")
        data_points = series.get("data", [])
        if not data_points:
            continue
        values = [v for point in data_points for v in (point.get("values") or []) if v is not None]
        if not values:
            continue
        avg_val = sum(values) / len(values)
        if "errors.server.rate" in metric_id:
            error_rate = avg_val
        elif "response.time" in metric_id:
            response_time = avg_val / 1000  # µs → ms
        elif "requestCount" in metric_id:
            request_count = avg_val

    return ServiceMetric(
        service_name=service_entity_id,
        entity_id=service_entity_id,
        error_rate=error_rate,
        request_count=request_count,
        response_time_ms=response_time,
        timestamp=datetime.now(tz=UTC),
    )


async def fetch_services() -> list[dict]:
    """Fetch all SERVICE entities from Dynatrace."""
    settings = get_settings()
    url = f"{settings.dynatrace_url}/api/v2/entities"
    params = {
        "entitySelector": "type(SERVICE)",
        "fields": "+properties.detectedName",
        "pageSize": 200,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            url, params=params, headers=_dt_headers(settings.dynatrace_api_token)
        )
        resp.raise_for_status()
        return resp.json().get("entities", [])
