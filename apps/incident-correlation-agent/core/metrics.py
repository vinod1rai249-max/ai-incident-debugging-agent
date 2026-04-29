from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

registry = CollectorRegistry()

incident_count = Gauge(
    "servicenow_incident_count",
    "Total open ServiceNow incidents",
    ["priority", "state"],
    registry=registry,
)

high_priority_incidents = Gauge(
    "servicenow_high_priority_incident_count",
    "Number of P1/P2 open incidents",
    registry=registry,
)

error_rate = Gauge(
    "dynatrace_service_error_rate",
    "Error rate from Dynatrace (percentage)",
    ["service_name"],
    registry=registry,
)

ai_analysis_duration = Histogram(
    "ai_analysis_duration_seconds",
    "Seconds taken by AI agent to complete analysis",
    buckets=[1, 2, 5, 10, 30, 60],
    registry=registry,
)

correlations_total = Counter(
    "correlation_found_total",
    "Total successful incident-trace correlations",
    registry=registry,
)

analysis_requests_total = Counter(
    "ai_analysis_requests_total",
    "Total AI analysis requests",
    ["status"],
    registry=registry,
)


def get_metrics_output() -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST
