from pydantic import BaseModel

from .incident import ServiceNowIncident
from .trace import DynatraceProblem, ServiceMetric


class CorrelationResult(BaseModel):
    incident: ServiceNowIncident
    matched_problems: list[DynatraceProblem] = []
    service_metrics: list[ServiceMetric] = []
    correlation_score: float = 0.0
    correlation_reasons: list[str] = []


class AIAnalysisResult(BaseModel):
    incident_number: str
    root_cause_summary: str
    contributing_factors: list[str] = []
    suggested_resolution: str
    confidence: str  # HIGH | MEDIUM | LOW
    related_services: list[str] = []
    recommended_actions: list[str] = []


class CorrelationAnalysis(BaseModel):
    correlation: CorrelationResult
    analysis: AIAnalysisResult | None = None
