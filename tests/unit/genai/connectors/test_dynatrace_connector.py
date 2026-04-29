"""Unit tests for DynatraceConnector and ObservabilityEvent."""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from pydantic import ValidationError

from genai.connectors.dynatrace_connector import _DEFAULT_FIXTURE, DynatraceConnector
from genai.connectors.models import ObservabilityEvent
from genai.rag.retrieval.base import Document

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connector() -> DynatraceConnector:
    return DynatraceConnector(fixture_path=_DEFAULT_FIXTURE)


def _minimal_raw(**overrides) -> dict:
    """Raw dict using fixture field names (log_id), as the connector would receive."""
    base = {
        "log_id": "dt_test_001",
        "timestamp": "2026-04-28T08:00:00Z",
        "level": "ERROR",
        "service_name": "test-service",
        "host": "worker-01",
        "environment": "production",
        "trace_id": "abc123",
        "span_id": "def456",
        "message": "Test error message",
        "error_type": "java.lang.RuntimeException",
        "stack_trace": "at Test.run(Test.java:1)",
        "tags": ["test"],
    }
    return {**base, **overrides}


def _minimal_event(**overrides) -> dict:
    """Dict using ObservabilityEvent field names (event_id) for direct model construction."""
    base = {
        "event_id": "dt_test_001",
        "timestamp": "2026-04-28T08:00:00Z",
        "level": "ERROR",
        "service_name": "test-service",
        "host": "worker-01",
        "environment": "production",
        "trace_id": "abc123",
        "span_id": "def456",
        "message": "Test error message",
        "error_type": "java.lang.RuntimeException",
        "stack_trace": "at Test.run(Test.java:1)",
        "tags": ["test"],
    }
    return {**base, **overrides}


# ---------------------------------------------------------------------------
# ObservabilityEvent model
# ---------------------------------------------------------------------------


class TestObservabilityEvent:
    def test_valid_event_parses(self) -> None:
        ev = ObservabilityEvent(**_minimal_event())
        assert ev.event_id == "dt_test_001"
        assert ev.level == "ERROR"
        assert ev.service_name == "test-service"

    def test_severity_error_maps_high(self) -> None:
        ev = ObservabilityEvent(**_minimal_event(level="ERROR"))
        assert ev.severity == "HIGH"

    def test_severity_warn_maps_medium(self) -> None:
        ev = ObservabilityEvent(**_minimal_event(level="WARN"))
        assert ev.severity == "MEDIUM"

    def test_severity_info_maps_low(self) -> None:
        ev = ObservabilityEvent(**_minimal_event(level="INFO"))
        assert ev.severity == "LOW"

    def test_severity_debug_maps_low(self) -> None:
        ev = ObservabilityEvent(**_minimal_event(level="DEBUG"))
        assert ev.severity == "LOW"

    def test_tags_default_empty_list(self) -> None:
        raw = {k: v for k, v in _minimal_event().items() if k != "tags"}
        ev = ObservabilityEvent(**raw)
        assert ev.tags == []

    def test_host_defaults_empty_string(self) -> None:
        raw = {k: v for k, v in _minimal_event().items() if k != "host"}
        ev = ObservabilityEvent(**raw)
        assert ev.host == ""

    def test_invalid_level_raises(self) -> None:
        with pytest.raises(ValidationError):
            ObservabilityEvent(**_minimal_event(level="CRITICAL"))

    def test_missing_required_message_raises(self) -> None:
        raw = {k: v for k, v in _minimal_event().items() if k != "message"}
        with pytest.raises(ValidationError):
            ObservabilityEvent(**raw)

    def test_missing_required_service_raises(self) -> None:
        raw = {k: v for k, v in _minimal_event().items() if k != "service_name"}
        with pytest.raises(ValidationError):
            ObservabilityEvent(**raw)

    def test_trace_and_span_ids_stored(self) -> None:
        ev = ObservabilityEvent(**_minimal_event(trace_id="trace-xyz", span_id="span-abc"))
        assert ev.trace_id == "trace-xyz"
        assert ev.span_id == "span-abc"


# ---------------------------------------------------------------------------
# DynatraceConnector — fetch_events()
# ---------------------------------------------------------------------------


class TestFetchEvents:
    def test_returns_ten_events(self) -> None:
        assert len(_connector().fetch_events()) == 10

    def test_all_events_are_observability_event(self) -> None:
        for ev in _connector().fetch_events():
            assert isinstance(ev, ObservabilityEvent)

    def test_all_have_non_empty_message(self) -> None:
        for ev in _connector().fetch_events():
            assert ev.message, f"{ev.event_id} has empty message"

    def test_all_have_non_empty_service_name(self) -> None:
        for ev in _connector().fetch_events():
            assert ev.service_name, f"{ev.event_id} has empty service_name"

    def test_all_events_are_production(self) -> None:
        for ev in _connector().fetch_events():
            assert ev.environment == "production"

    def test_covers_error_level(self) -> None:
        levels = {ev.level for ev in _connector().fetch_events()}
        assert "ERROR" in levels

    def test_covers_warn_level(self) -> None:
        levels = {ev.level for ev in _connector().fetch_events()}
        assert "WARN" in levels

    def test_covers_hl7_order_failures(self) -> None:
        messages = " ".join(ev.message for ev in _connector().fetch_events())
        assert "ORM" in messages or "order" in messages.lower()

    def test_covers_hl7_result_failures(self) -> None:
        messages = " ".join(ev.message for ev in _connector().fetch_events())
        assert "ORU" in messages or "result" in messages.lower()

    def test_phi_masking_applied_to_message(self) -> None:
        raw_data = [{**_minimal_raw(), "message": "Patient MRN-000001 result failed"}]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(raw_data, f)
            tmp_path = f.name
        try:
            events = DynatraceConnector(fixture_path=tmp_path).fetch_events()
            assert "[MRN]" in events[0].message
            assert "MRN-000001" not in events[0].message
        finally:
            os.unlink(tmp_path)

    def test_phi_masking_applied_to_stack_trace(self) -> None:
        raw_data = [{**_minimal_raw(), "stack_trace": "error for 192.168.1.10 at Test.run"}]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(raw_data, f)
            tmp_path = f.name
        try:
            events = DynatraceConnector(fixture_path=tmp_path).fetch_events()
            assert "[IP]" in events[0].stack_trace
            assert "192.168.1.10" not in events[0].stack_trace
        finally:
            os.unlink(tmp_path)

    def test_all_have_trace_id(self) -> None:
        for ev in _connector().fetch_events():
            assert ev.trace_id, f"{ev.event_id} is missing trace_id"

    def test_all_have_span_id(self) -> None:
        for ev in _connector().fetch_events():
            assert ev.span_id, f"{ev.event_id} is missing span_id"


# ---------------------------------------------------------------------------
# DynatraceConnector — to_documents()
# ---------------------------------------------------------------------------


class TestToDocuments:
    def test_returns_ten_documents(self) -> None:
        assert len(_connector().to_documents()) == 10

    def test_all_source_is_dynatrace(self) -> None:
        for doc in _connector().to_documents():
            assert doc.source == "dynatrace", f"Expected 'dynatrace', got '{doc.source}'"

    def test_all_content_non_empty(self) -> None:
        for doc in _connector().to_documents():
            assert doc.content.strip(), f"Empty content for {doc.metadata.get('log_id')}"

    def test_metadata_has_required_keys(self) -> None:
        required = {
            "log_id",
            "description",
            "severity",
            "service",
            "level",
            "error_type",
            "source_system",
        }
        for doc in _connector().to_documents():
            for key in required:
                assert key in doc.metadata, (
                    f"Missing '{key}' in metadata for {doc.metadata.get('log_id')}"
                )

    def test_source_system_metadata_is_dynatrace(self) -> None:
        for doc in _connector().to_documents():
            assert doc.metadata["source_system"] == "dynatrace"

    def test_severity_values_are_valid(self) -> None:
        valid = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        for doc in _connector().to_documents():
            assert doc.metadata["severity"] in valid, (
                f"Invalid severity '{doc.metadata['severity']}'"
            )

    def test_level_metadata_preserved(self) -> None:
        for doc in _connector().to_documents():
            assert doc.metadata["level"] in {"ERROR", "WARN", "INFO", "DEBUG"}

    def test_documents_are_document_instances(self) -> None:
        for doc in _connector().to_documents():
            assert isinstance(doc, Document)

    def test_content_includes_error_type(self) -> None:
        docs = _connector().to_documents()
        docs_with_error_type = [d for d in docs if "Exception" in d.content or "Error" in d.content]
        assert docs_with_error_type, "No exception type found in any document content"

    def test_content_includes_stack_trace(self) -> None:
        docs = _connector().to_documents()
        docs_with_stack = [d for d in docs if "at " in d.content]
        assert docs_with_stack, "No stack trace content found in any document"

    def test_custom_fixture_path(self) -> None:
        raw_data = [_minimal_raw(log_id="custom_001")]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(raw_data, f)
            tmp_path = f.name
        try:
            docs = DynatraceConnector(fixture_path=tmp_path).to_documents()
            assert len(docs) == 1
            assert docs[0].source == "dynatrace"
            assert docs[0].metadata["log_id"] == "custom_001"
        finally:
            os.unlink(tmp_path)

    def test_error_level_docs_have_high_severity(self) -> None:
        docs = _connector().to_documents()
        error_docs = [d for d in docs if d.metadata["level"] == "ERROR"]
        for doc in error_docs:
            assert doc.metadata["severity"] == "HIGH"

    def test_warn_level_docs_have_medium_severity(self) -> None:
        docs = _connector().to_documents()
        warn_docs = [d for d in docs if d.metadata["level"] == "WARN"]
        for doc in warn_docs:
            assert doc.metadata["severity"] == "MEDIUM"
