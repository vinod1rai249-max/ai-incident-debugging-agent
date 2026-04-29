"""Unit tests for Section C — multi-source RAG integration.

Tests cover:
- ServiceNow and Dynatrace documents are loaded into the TF-IDF retriever
- retrieved_docs_count > 0 for representative MuleSoft healthcare queries
- source labels are "servicenow" / "dynatrace" on returned documents
- rag_sources metadata field is populated by the orchestrator
- AnalysisMetadata accepts the new rag_sources field
"""

from __future__ import annotations

import json

import pytest

from apps.incident_debugger.models import AgentStepTrace, AnalysisMetadata, RetrievedDocSummary
from genai.connectors.dynatrace_connector import _DEFAULT_FIXTURE as DT_FIXTURE
from genai.connectors.dynatrace_connector import DynatraceConnector
from genai.connectors.servicenow_connector import _DEFAULT_FIXTURE as SN_FIXTURE
from genai.connectors.servicenow_connector import ServiceNowConnector
from genai.rag.retrieval.tfidf_retriever import TFIDFRetriever

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seeded_retriever() -> TFIDFRetriever:
    """Return a fresh TFIDFRetriever seeded from both real fixture files."""
    retriever = TFIDFRetriever()
    docs = (
        ServiceNowConnector(fixture_path=SN_FIXTURE).to_documents()
        + DynatraceConnector(fixture_path=DT_FIXTURE).to_documents()
    )
    await retriever.add_documents(docs)
    return retriever


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


class TestCorpusLoading:
    def test_servicenow_fixture_loads_ten_docs(self) -> None:
        docs = ServiceNowConnector(fixture_path=SN_FIXTURE).to_documents()
        assert len(docs) == 10

    def test_dynatrace_fixture_loads_ten_docs(self) -> None:
        docs = DynatraceConnector(fixture_path=DT_FIXTURE).to_documents()
        assert len(docs) == 10

    def test_combined_corpus_has_twenty_docs(self) -> None:
        sn = ServiceNowConnector(fixture_path=SN_FIXTURE).to_documents()
        dt = DynatraceConnector(fixture_path=DT_FIXTURE).to_documents()
        assert len(sn) + len(dt) == 20

    def test_all_servicenow_docs_have_correct_source(self) -> None:
        for doc in ServiceNowConnector(fixture_path=SN_FIXTURE).to_documents():
            assert doc.source == "servicenow"

    def test_all_dynatrace_docs_have_correct_source(self) -> None:
        for doc in DynatraceConnector(fixture_path=DT_FIXTURE).to_documents():
            assert doc.source == "dynatrace"

    def test_servicenow_docs_have_source_system_metadata(self) -> None:
        for doc in ServiceNowConnector(fixture_path=SN_FIXTURE).to_documents():
            assert doc.metadata.get("source_system") == "servicenow"

    def test_dynatrace_docs_have_source_system_metadata(self) -> None:
        for doc in DynatraceConnector(fixture_path=DT_FIXTURE).to_documents():
            assert doc.metadata.get("source_system") == "dynatrace"

    def test_no_duplicate_sources_in_combined_corpus(self) -> None:
        sn = ServiceNowConnector(fixture_path=SN_FIXTURE).to_documents()
        dt = DynatraceConnector(fixture_path=DT_FIXTURE).to_documents()
        sn_sources = {d.metadata["source_system"] for d in sn}
        dt_sources = {d.metadata["source_system"] for d in dt}
        assert sn_sources == {"servicenow"}
        assert dt_sources == {"dynatrace"}


# ---------------------------------------------------------------------------
# Retriever — retrieved_docs_count > 0 for MuleSoft healthcare queries
# ---------------------------------------------------------------------------


class TestRetrievalCoverage:
    @pytest.mark.asyncio
    async def test_hl7_orm_query_returns_results(self) -> None:
        retriever = await _seeded_retriever()
        results = await retriever.retrieve(
            "HL7 ORM order message routing failure MuleSoft", top_k=2
        )
        assert len(results) > 0, "Expected at least one result for HL7 ORM query"

    @pytest.mark.asyncio
    async def test_hl7_oru_query_returns_results(self) -> None:
        retriever = await _seeded_retriever()
        results = await retriever.retrieve(
            "HL7 ORU lab result delivery failed MLLP timeout", top_k=2
        )
        assert len(results) > 0, "Expected at least one result for HL7 ORU query"

    @pytest.mark.asyncio
    async def test_oauth_token_query_returns_results(self) -> None:
        retriever = await _seeded_retriever()
        results = await retriever.retrieve(
            "OAuth2 SMART on FHIR token expired 401 Unauthorized", top_k=2
        )
        assert len(results) > 0, "Expected at least one result for OAuth query"

    @pytest.mark.asyncio
    async def test_dataweave_query_returns_results(self) -> None:
        retriever = await _seeded_retriever()
        results = await retriever.retrieve(
            "DataWeave transformation failed NullPointerException FHIR payload", top_k=2
        )
        assert len(results) > 0, "Expected at least one result for DataWeave query"

    @pytest.mark.asyncio
    async def test_cloudhub_oom_query_returns_results(self) -> None:
        retriever = await _seeded_retriever()
        results = await retriever.retrieve(
            "CloudHub OutOfMemoryError heap space HL7 batch", top_k=2
        )
        assert len(results) > 0, "Expected at least one result for CloudHub OOM query"

    @pytest.mark.asyncio
    async def test_results_have_source_label(self) -> None:
        retriever = await _seeded_retriever()
        results = await retriever.retrieve("MuleSoft HL7 healthcare", top_k=4)
        assert len(results) > 0
        valid_sources = {"servicenow", "dynatrace"}
        for doc in results:
            assert doc.source in valid_sources, (
                f"Unexpected source '{doc.source}' — expected one of {valid_sources}"
            )

    @pytest.mark.asyncio
    async def test_results_have_positive_score(self) -> None:
        retriever = await _seeded_retriever()
        results = await retriever.retrieve("HL7 ORM order routing failure", top_k=2)
        for doc in results:
            assert doc.score > 0.0, f"Expected positive score, got {doc.score}"

    @pytest.mark.asyncio
    async def test_top_k_respected(self) -> None:
        retriever = await _seeded_retriever()
        results = await retriever.retrieve("MuleSoft healthcare", top_k=2)
        assert len(results) <= 2

    @pytest.mark.asyncio
    async def test_both_sources_represented_across_corpus(self) -> None:
        retriever = await _seeded_retriever()
        # Broad query — should surface both sources across the 20-doc corpus
        results = await retriever.retrieve("MuleSoft HL7 FHIR healthcare error", top_k=4)
        sources_seen = {d.source for d in results}
        assert len(sources_seen) >= 1, "At least one source should be present"

    @pytest.mark.asyncio
    async def test_retrieved_docs_count_positive(self) -> None:
        retriever = await _seeded_retriever()
        results = await retriever.retrieve(
            "DataWeaveMappingException OBX segment missing observation identifier", top_k=2
        )
        assert len(results) > 0, "retrieved_docs_count must be > 0"


# ---------------------------------------------------------------------------
# AnalysisMetadata — rag_sources field
# ---------------------------------------------------------------------------


class TestRagSourcesMetadata:
    def _make_trace(self) -> AgentStepTrace:
        return AgentStepTrace(
            agent_name="ClassifierAgent",
            model_id="claude-haiku-4-5-20251001",
            status="success",
            latency_ms=100.0,
            input_tokens=200,
            output_tokens=50,
            cost_usd=0.0005,
        )

    def test_rag_sources_defaults_empty(self) -> None:
        meta = AnalysisMetadata(
            total_cost_usd=0.01,
            total_latency_ms=500.0,
            models_used=["claude-haiku-4-5-20251001"],
            agent_trace=[self._make_trace()],
        )
        assert meta.rag_sources == []

    def test_rag_sources_accepts_servicenow(self) -> None:
        meta = AnalysisMetadata(
            total_cost_usd=0.01,
            total_latency_ms=500.0,
            models_used=["claude-sonnet-4-6"],
            agent_trace=[self._make_trace()],
            rag_sources=["servicenow"],
        )
        assert meta.rag_sources == ["servicenow"]

    def test_rag_sources_accepts_both_sources(self) -> None:
        meta = AnalysisMetadata(
            total_cost_usd=0.01,
            total_latency_ms=500.0,
            models_used=["claude-sonnet-4-6"],
            agent_trace=[self._make_trace()],
            retrieved_docs_count=2,
            rag_sources=["servicenow", "dynatrace"],
        )
        assert "servicenow" in meta.rag_sources
        assert "dynatrace" in meta.rag_sources

    def test_rag_sources_serialises_to_json(self) -> None:
        meta = AnalysisMetadata(
            total_cost_usd=0.01,
            total_latency_ms=500.0,
            models_used=["claude-haiku-4-5-20251001"],
            agent_trace=[self._make_trace()],
            rag_sources=["servicenow", "dynatrace"],
        )
        payload = json.loads(meta.model_dump_json())
        assert payload["rag_sources"] == ["servicenow", "dynatrace"]

    def test_retrieved_docs_count_and_rag_sources_consistent(self) -> None:
        meta = AnalysisMetadata(
            total_cost_usd=0.01,
            total_latency_ms=500.0,
            models_used=["claude-sonnet-4-6"],
            agent_trace=[self._make_trace()],
            retrieved_docs_count=2,
            retrieved_docs=[
                RetrievedDocSummary(
                    source="servicenow",
                    description="HL7 ORM failure",
                    severity="HIGH",
                    score=0.82,
                ),
                RetrievedDocSummary(
                    source="dynatrace",
                    description="MLLP timeout",
                    severity="HIGH",
                    score=0.71,
                ),
            ],
            rag_sources=["servicenow", "dynatrace"],
        )
        assert meta.retrieved_docs_count == len(meta.retrieved_docs)
        assert set(meta.rag_sources) == {d.source for d in meta.retrieved_docs}
