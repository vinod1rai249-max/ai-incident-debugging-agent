"""Prometheus metrics for the Incident Debugger pipeline."""

from prometheus_client import Counter, Histogram

# ── Existing pipeline counters ─────────────────────────────────────────────

incident_analysis_total = Counter(
    "incident_analysis_total",
    "Total incident analyses dispatched (success + degraded + failure)",
    ["severity", "environment"],
)

incident_analysis_success_total = Counter(
    "incident_analysis_success_total",
    "Incident analyses completed without any agent fallback",
    ["severity", "environment"],
)

incident_analysis_failure_total = Counter(
    "incident_analysis_failure_total",
    "Incident analyses aborted due to a blocking agent failure",
    ["environment"],
)

degraded_response_total = Counter(
    "degraded_response_total",
    "Incident analyses returned with degraded=True (non-blocking agent fallback)",
    ["environment"],
)

# ── Existing pipeline histograms ───────────────────────────────────────────

incident_analysis_duration_seconds = Histogram(
    "incident_analysis_duration_seconds",
    "End-to-end pipeline duration in seconds",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
)

incident_agent_duration_seconds = Histogram(
    "incident_agent_duration_seconds",
    "Per-agent call duration in seconds",
    ["agent_name"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0],
)

incident_agent_cost_usd = Histogram(
    "incident_agent_cost_usd",
    "Per-agent call cost in USD",
    ["agent_name", "model"],
    buckets=[0.0001, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
)

incident_confidence_score = Histogram(
    "incident_confidence_score",
    "Confidence score distribution per severity level",
    ["severity"],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
)

incident_cost_usd_total = Histogram(
    "incident_cost_usd_total",
    "Total per-incident cost in USD",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1],
)

# ── RAG retrieval metrics ──────────────────────────────────────────────────

retrieved_docs_count = Histogram(
    "retrieved_docs_count",
    "Number of RAG documents retrieved per incident analysis",
    buckets=[0, 1, 2, 3, 4, 5, 10],
)

rag_source_hits_total = Counter(
    "rag_source_hits_total",
    "RAG document retrievals counted by source system (servicenow / dynatrace)",
    ["source"],
)
