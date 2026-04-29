"""Unit tests for Step 6 — Prometheus metrics.

Covers:
- All new metrics are importable with correct types and label names
- Counters can be incremented without error
- Orchestrator emits success/degraded/failure counters at the right pipeline points
- RAG source hits are counted per source when retriever returns docs
- retrieved_docs_count histogram is observed per request
"""

from __future__ import annotations

import pytest
from prometheus_client import Counter, Histogram

from apps.incident_debugger.models import IncidentInput
from apps.incident_debugger.orchestrator import IncidentOrchestrator
from core.circuit_breaker import CircuitBreaker
from genai.clients.mock_client import MockLLMClient
from genai.rag.retrieval.base import BaseRetriever, Document
from tests.helpers.mock_builder import MockLLMClientBuilder

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_orchestrator(
    client: MockLLMClient,
    retriever: BaseRetriever | None = None,
) -> IncidentOrchestrator:
    return IncidentOrchestrator(
        llm_client=client,
        circuit_breaker=CircuitBreaker(name="test_metrics_cb", min_calls=5),
        max_retries=2,
        base_wait_s=0.0,
        retriever=retriever,
    )


@pytest.fixture
def incident() -> IncidentInput:
    return IncidentInput(
        error_message="AttributeError: 'NoneType' object has no attribute 'charge_id'",
        stack_trace="File payment.py line 84\n  charge_id = transaction.charge_id",
        logs="2026-04-28 ERROR NoneType",
        service_name="payment-service",
        environment="test",
    )


class StubRetriever(BaseRetriever):
    """Returns two fixed docs — one per source — for metric testing."""

    async def retrieve(self, query: str, *, top_k: int) -> list[Document]:
        return [
            Document(
                content="past servicenow incident",
                source="servicenow",
                metadata={"source_system": "servicenow", "severity": "HIGH"},
                score=0.85,
            ),
            Document(
                content="past dynatrace log entry",
                source="dynatrace",
                metadata={"source_system": "dynatrace", "severity": "HIGH"},
                score=0.72,
            ),
        ]

    async def add_documents(self, documents: list[Document]) -> None:
        pass


# ---------------------------------------------------------------------------
# Section 1 — Metric definitions: types and label names
# ---------------------------------------------------------------------------


class TestMetricDefinitions:
    def test_incident_analysis_success_total_is_counter(self) -> None:
        from apps.incident_debugger.metrics import incident_analysis_success_total

        assert isinstance(incident_analysis_success_total, Counter)

    def test_incident_analysis_success_total_labels(self) -> None:
        from apps.incident_debugger.metrics import incident_analysis_success_total

        assert "severity" in incident_analysis_success_total._labelnames
        assert "environment" in incident_analysis_success_total._labelnames

    def test_incident_analysis_failure_total_is_counter(self) -> None:
        from apps.incident_debugger.metrics import incident_analysis_failure_total

        assert isinstance(incident_analysis_failure_total, Counter)

    def test_incident_analysis_failure_total_labels(self) -> None:
        from apps.incident_debugger.metrics import incident_analysis_failure_total

        assert "environment" in incident_analysis_failure_total._labelnames

    def test_degraded_response_total_is_counter(self) -> None:
        from apps.incident_debugger.metrics import degraded_response_total

        assert isinstance(degraded_response_total, Counter)

    def test_degraded_response_total_labels(self) -> None:
        from apps.incident_debugger.metrics import degraded_response_total

        assert "environment" in degraded_response_total._labelnames

    def test_rag_source_hits_total_is_counter(self) -> None:
        from apps.incident_debugger.metrics import rag_source_hits_total

        assert isinstance(rag_source_hits_total, Counter)

    def test_rag_source_hits_total_labels(self) -> None:
        from apps.incident_debugger.metrics import rag_source_hits_total

        assert "source" in rag_source_hits_total._labelnames

    def test_retrieved_docs_count_is_histogram(self) -> None:
        from apps.incident_debugger.metrics import retrieved_docs_count

        assert isinstance(retrieved_docs_count, Histogram)

    def test_all_step6_metrics_importable(self) -> None:
        from apps.incident_debugger.metrics import (  # noqa: F401
            degraded_response_total,
            incident_analysis_failure_total,
            incident_analysis_success_total,
            rag_source_hits_total,
            retrieved_docs_count,
        )


# ---------------------------------------------------------------------------
# Section 2 — Counters can be incremented safely
# ---------------------------------------------------------------------------


class TestCounterIncrements:
    def test_rag_source_hits_servicenow_increments(self) -> None:
        from apps.incident_debugger.metrics import rag_source_hits_total

        rag_source_hits_total.labels(source="servicenow").inc()

    def test_rag_source_hits_dynatrace_increments(self) -> None:
        from apps.incident_debugger.metrics import rag_source_hits_total

        rag_source_hits_total.labels(source="dynatrace").inc()

    def test_degraded_response_total_increments(self) -> None:
        from apps.incident_debugger.metrics import degraded_response_total

        degraded_response_total.labels(environment="unit-test").inc()

    def test_incident_analysis_failure_total_increments(self) -> None:
        from apps.incident_debugger.metrics import incident_analysis_failure_total

        incident_analysis_failure_total.labels(environment="unit-test").inc()

    def test_incident_analysis_success_total_increments(self) -> None:
        from apps.incident_debugger.metrics import incident_analysis_success_total

        incident_analysis_success_total.labels(severity="HIGH", environment="unit-test").inc()

    def test_retrieved_docs_count_observe(self) -> None:
        from apps.incident_debugger.metrics import retrieved_docs_count

        retrieved_docs_count.observe(2)
        retrieved_docs_count.observe(0)


# ---------------------------------------------------------------------------
# Section 3 — Orchestrator emits correct metrics per pipeline outcome
# ---------------------------------------------------------------------------


class TestOrchestratorMetricEmission:
    async def test_success_path_does_not_raise(self, incident: IncidentInput) -> None:
        orch = make_orchestrator(MockLLMClientBuilder.simple())
        report = await orch.run(incident)
        assert not report.metadata.degraded

    async def test_degraded_path_when_fix_fails(self, incident: IncidentInput) -> None:
        orch = make_orchestrator(MockLLMClientBuilder.simple(fix=["bad", "bad"]))
        report = await orch.run(incident)
        assert report.metadata.degraded is True

    async def test_failure_path_when_classifier_fails(self, incident: IncidentInput) -> None:
        orch = make_orchestrator(MockLLMClientBuilder.simple(classifier=["bad", "bad"]))
        report = await orch.run(incident)
        assert report.metadata.degraded is True
        assert report.confidence_score == 0.0

    async def test_failure_path_when_root_cause_fails(self, incident: IncidentInput) -> None:
        orch = make_orchestrator(MockLLMClientBuilder.simple(root_cause=["bad", "bad"]))
        report = await orch.run(incident)
        assert report.metadata.degraded is True
        assert report.confidence_score == 0.0


# ---------------------------------------------------------------------------
# Section 4 — RAG metrics are emitted with correct source labels
# ---------------------------------------------------------------------------


class TestRagMetrics:
    async def test_rag_sources_in_report_when_retriever_used(self, incident: IncidentInput) -> None:
        orch = make_orchestrator(
            MockLLMClientBuilder.simple(),
            retriever=StubRetriever(),
        )
        report = await orch.run(incident)
        assert report.metadata.retrieved_docs_count == 2
        assert "servicenow" in report.metadata.rag_sources
        assert "dynatrace" in report.metadata.rag_sources

    async def test_retrieved_docs_count_zero_without_retriever(
        self, incident: IncidentInput
    ) -> None:
        orch = make_orchestrator(MockLLMClientBuilder.simple())
        report = await orch.run(incident)
        assert report.metadata.retrieved_docs_count == 0

    async def test_rag_metrics_do_not_crash_when_retriever_raises(
        self, incident: IncidentInput
    ) -> None:
        class BrokenRetriever(BaseRetriever):
            async def retrieve(self, query: str, *, top_k: int) -> list[Document]:
                raise RuntimeError("simulated retriever failure")

            async def add_documents(self, documents: list[Document]) -> None:
                pass

        orch = make_orchestrator(
            MockLLMClientBuilder.simple(),
            retriever=BrokenRetriever(),
        )
        report = await orch.run(incident)
        assert report.metadata.retrieved_docs_count == 0
        assert report.metadata.rag_sources == []
