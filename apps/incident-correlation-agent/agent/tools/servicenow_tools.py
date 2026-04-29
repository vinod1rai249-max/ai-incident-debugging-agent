from base64 import b64encode

import httpx
from models.incident import ServiceNowIncident

from core.config import get_settings
from core.logging_config import get_logger

logger = get_logger(__name__)

INCIDENT_FIELDS = (
    "sys_id,number,short_description,description,state,priority,"
    "urgency,impact,category,assignment_group,assigned_to,"
    "opened_at,sys_updated_on,cmdb_ci"
)


def _auth_header(user: str, password: str) -> str:
    token = b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {token}"


async def fetch_incidents(
    state_query: str = "state=1^ORstate=2^ORstate=3",
    limit: int | None = None,
) -> list[ServiceNowIncident]:
    settings = get_settings()
    lim = limit or settings.servicenow_incident_limit
    url = f"{settings.servicenow_url}/api/now/table/incident"

    params = {
        "sysparm_query": state_query,
        "sysparm_limit": lim,
        "sysparm_fields": INCIDENT_FIELDS,
        "sysparm_display_value": "false",
    }
    headers = {
        "Authorization": _auth_header(settings.servicenow_user, settings.servicenow_password),
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        records = resp.json().get("result", [])

    incidents = []
    for r in records:
        try:
            incidents.append(ServiceNowIncident(**r))
        except Exception as exc:
            logger.warning("incident_parse_error", sys_id=r.get("sys_id"), error=str(exc))

    logger.info("incidents_fetched", count=len(incidents))
    return incidents


async def fetch_incident_by_number(number: str) -> ServiceNowIncident | None:
    settings = get_settings()
    url = f"{settings.servicenow_url}/api/now/table/incident"
    params = {
        "sysparm_query": f"number={number}",
        "sysparm_limit": 1,
        "sysparm_fields": INCIDENT_FIELDS,
    }
    headers = {
        "Authorization": _auth_header(settings.servicenow_user, settings.servicenow_password),
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        records = resp.json().get("result", [])

    if not records:
        return None
    return ServiceNowIncident(**records[0])
