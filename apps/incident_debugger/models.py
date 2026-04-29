from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Literal

import structlog
from pydantic import BaseModel, Field, model_validator

_logger = structlog.get_logger(__name__)


class SeverityLevel(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class IncidentInput(BaseModel):
    error_message: str = Field(..., min_length=1)
    stack_trace: str = Field(..., min_length=1)
    logs: str = Field(..., min_length=1)
    code_snippet: str | None = Field(default=None)
    service_name: str | None = Field(default=None)
    environment: str = Field(default="production")
    # Dev-only test hooks — silently ignored when APP_ENV=production
    force_degraded: bool = Field(default=False)
    force_blocking_failure: bool = Field(default=False)


class PlannerResult(BaseModel):
    steps: list[str] = Field(..., min_length=1)
    priority_signals: list[str]
    estimated_complexity: Literal["simple", "moderate", "complex"]


class TriageResult(BaseModel):
    error_category: str
    key_signals: list[str]
    analysis_plan: str


class RootCauseResult(BaseModel):
    root_cause: str
    contributing_factors: list[str]
    affected_components: list[str]


_ROLLBACK_PLAN_MIN_WARN_LEN = 10


class FixResult(BaseModel):
    quick_fix: str
    long_term_fix: str = ""
    validation_steps: list[str] = Field(..., min_length=1)
    rollback_plan: str = ""

    @model_validator(mode="after")
    def _warn_short_rollback_plan(self) -> FixResult:
        if self.rollback_plan and len(self.rollback_plan) < _ROLLBACK_PLAN_MIN_WARN_LEN:
            _logger.warning(
                "fix_result.rollback_plan_too_short",
                length=len(self.rollback_plan),
                rollback_plan=self.rollback_plan,
                threshold=_ROLLBACK_PLAN_MIN_WARN_LEN,
            )
        return self


class CriticResult(BaseModel):
    severity: SeverityLevel
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    review_notes: str


class AgentStepTrace(BaseModel):
    agent_name: str
    model_id: str
    status: Literal["success", "error", "partial", "skipped"]
    latency_ms: float = Field(ge=0.0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    error: str | None = None


class RetrievedDocSummary(BaseModel):
    source: str
    description: str
    severity: str
    score: float = Field(ge=0.0)


class AnalysisMetadata(BaseModel):
    total_cost_usd: float = Field(ge=0.0)
    total_latency_ms: float = Field(ge=0.0)
    models_used: list[str]
    agent_trace: list[AgentStepTrace]
    degraded: bool = False
    failure_reason: str | None = None
    retrieved_docs_count: int = Field(default=0, ge=0)
    retrieved_docs: list[RetrievedDocSummary] = Field(default_factory=list)
    rag_sources: list[str] = Field(default_factory=list)


class IncidentReport(BaseModel):
    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    root_cause: str
    severity: SeverityLevel
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    quick_fix: str
    long_term_fix: str
    validation_steps: list[str]
    rollback_plan: str
    metadata: AnalysisMetadata


class AgentEnvelope(BaseModel):
    task: str
    status: Literal["success", "error", "partial"]
    artifacts: dict  # type: ignore[type-arg]
    errors: list[str] = Field(default_factory=list)
    next_agent: str
    cost_usd: float = Field(default=0.0, ge=0.0)
    latency_ms: float = Field(default=0.0, ge=0.0)
