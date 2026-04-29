from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, field_validator


class DynatraceProblem(BaseModel):
    problem_id: str
    display_id: str
    title: str
    status: str  # OPEN | CLOSED
    severity_level: str  # AVAILABILITY | ERROR | PERFORMANCE | RESOURCE_CONTENTION
    impact_level: str  # APPLICATION | ENVIRONMENT | INFRASTRUCTURE | SERVICE
    start_time: datetime
    end_time: datetime | None = None
    impacted_entities: list[dict[str, Any]] = []
    root_cause_entity: dict[str, Any] | None = None
    affected_counts: dict[str, int] = {}

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def parse_epoch_ms(cls, v: Any) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / 1000, tz=UTC)
        return v

    @property
    def service_names(self) -> list[str]:
        return [
            e.get("name", "")
            for e in self.impacted_entities
            if e.get("entityId", {}).get("type") == "SERVICE"
        ]


class ServiceMetric(BaseModel):
    service_name: str
    entity_id: str
    error_rate: float | None = None
    request_count: float | None = None
    response_time_ms: float | None = None
    timestamp: datetime
