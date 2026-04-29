from datetime import datetime

from pydantic import BaseModel, field_validator


class ServiceNowIncident(BaseModel):
    sys_id: str
    number: str
    short_description: str
    description: str | None = None
    state: str = ""
    priority: str = ""
    urgency: str = ""
    impact: str = ""
    category: str | None = None
    assignment_group: str | None = None
    assigned_to: str | None = None
    opened_at: datetime | None = None
    sys_updated_on: datetime | None = None
    cmdb_ci: str | None = None

    @field_validator("opened_at", "sys_updated_on", mode="before")
    @classmethod
    def parse_sn_datetime(cls, v: str | None) -> datetime | None:
        if not v:
            return None
        try:
            return datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None

    @property
    def service_name(self) -> str:
        return self.cmdb_ci or ""

    @property
    def is_high_priority(self) -> bool:
        return self.priority.startswith("1") or self.priority.startswith("2")

    @property
    def state_label(self) -> str:
        state_map = {"1": "New", "2": "In Progress", "3": "On Hold", "6": "Resolved", "7": "Closed"}
        return state_map.get(self.state, self.state)
