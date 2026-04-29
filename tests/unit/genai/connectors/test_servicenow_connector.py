"""Unit tests for ServiceNowConnector and PHI masker."""

from __future__ import annotations

import json

from core.phi_masker import mask_dict, mask_phi
from genai.connectors.servicenow_connector import (
    _DEFAULT_FIXTURE,
    ServiceNowConnector,
    ServiceNowIncident,
)
from genai.rag.retrieval.base import Document

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURE_PATH = _DEFAULT_FIXTURE


def _connector() -> ServiceNowConnector:
    return ServiceNowConnector(fixture_path=FIXTURE_PATH)


# ---------------------------------------------------------------------------
# PHI masker — mask_phi()
# ---------------------------------------------------------------------------


class TestMaskPhi:
    def test_masks_ssn(self) -> None:
        assert "[SSN]" in mask_phi("Patient SSN 123-45-6789 on file")

    def test_masks_email(self) -> None:
        assert "[EMAIL]" in mask_phi("Contact dr.smith@hospital.org for follow-up")

    def test_masks_ip(self) -> None:
        assert "[IP]" in mask_phi("Connection from 192.168.1.42 timed out")

    def test_masks_bearer_token(self) -> None:
        assert "[TOKEN]" in mask_phi("Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.payload.sig")

    def test_masks_jwt(self) -> None:
        # Raw JWT embedded in text (no Bearer/token= prefix) is caught by the JWT pattern
        assert "[JWT]" in mask_phi(
            "Found in log: eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123sig"
        )

    def test_masks_mrn(self) -> None:
        assert "[MRN]" in mask_phi("Patient MRN-000123 admitted to ICU")

    def test_masks_pat_id(self) -> None:
        assert "[MRN]" in mask_phi("Processing PAT-98765 lab results")

    def test_masks_dob(self) -> None:
        assert "[DOB]" in mask_phi("DOB: 03/15/1975 does not match records")

    def test_masks_phone(self) -> None:
        assert "[PHONE]" in mask_phi("Call 555-867-5309 for support")

    def test_masks_generic_secret(self) -> None:
        assert "[SECRET]" in mask_phi("client_secret=s3cr3tV@lue123 used in request")

    def test_leaves_non_phi_unchanged(self) -> None:
        text = "DataWeave transformation failed on OBX segment"
        assert mask_phi(text) == text

    def test_empty_string_unchanged(self) -> None:
        assert mask_phi("") == ""

    def test_non_string_unchanged(self) -> None:
        assert mask_phi(None) is None  # type: ignore[arg-type]

    def test_multiple_patterns_in_one_string(self) -> None:
        text = "MRN-001 DOB: 01/01/1980 email test@example.com SSN 111-22-3333"
        result = mask_phi(text)
        assert "[MRN]" in result
        assert "[DOB]" in result
        assert "[EMAIL]" in result
        assert "[SSN]" in result
        assert "test@example.com" not in result


class TestMaskDict:
    def test_masks_all_string_values(self) -> None:
        data = {"description": "MRN-001 patient", "severity": "HIGH"}
        result = mask_dict(data)
        assert "[MRN]" in result["description"]
        assert result["severity"] == "HIGH"

    def test_preserves_non_string_values(self) -> None:
        data = {"count": 42, "active": True}  # type: ignore[dict-item]
        result = mask_dict(data)  # type: ignore[arg-type]
        assert result["count"] == 42
        assert result["active"] is True


# ---------------------------------------------------------------------------
# ServiceNowIncident value object
# ---------------------------------------------------------------------------


class TestServiceNowIncident:
    def _raw(self) -> dict:
        return {
            "sys_id": "abc123",
            "number": "INC0010001",
            "short_description": "HL7 ORM failure",
            "description": "Detailed description",
            "assignment_group": "MuleSoft Support",
            "category": "Integration",
            "subcategory": "HL7 ORM",
            "priority": "2 - High",
            "state": "Resolved",
            "service_name": "hl7-order-routing-api",
            "environment": "production",
            "error_message": "HL7RouterException: ORC-2 is null",
            "stack_trace": "at HL7Router.route(HL7Router.java:112)",
            "resolution_notes": "Added null guard on ORC-2",
            "resolved_at": "2026-04-10T14:30:00Z",
            "tags": ["hl7", "orm"],
        }

    def test_severity_maps_priority(self) -> None:
        inc = ServiceNowIncident(self._raw())
        assert inc.severity == "HIGH"

    def test_severity_critical(self) -> None:
        raw = {**self._raw(), "priority": "1 - Critical"}
        assert ServiceNowIncident(raw).severity == "CRITICAL"

    def test_severity_unknown_defaults_medium(self) -> None:
        raw = {**self._raw(), "priority": "99 - Unknown"}
        assert ServiceNowIncident(raw).severity == "MEDIUM"

    def test_all_fields_populated(self) -> None:
        inc = ServiceNowIncident(self._raw())
        assert inc.number == "INC0010001"
        assert inc.assignment_group == "MuleSoft Support"
        assert inc.service_name == "hl7-order-routing-api"
        assert inc.tags == ["hl7", "orm"]

    def test_missing_fields_default_empty(self) -> None:
        inc = ServiceNowIncident({})
        assert inc.number == ""
        assert inc.tags == []


# ---------------------------------------------------------------------------
# ServiceNowConnector — fetch_incidents()
# ---------------------------------------------------------------------------


class TestFetchIncidents:
    def test_returns_ten_incidents(self) -> None:
        incidents = _connector().fetch_incidents()
        assert len(incidents) == 10

    def test_all_mulesoft_support_assignment(self) -> None:
        for inc in _connector().fetch_incidents():
            assert inc.assignment_group == "MuleSoft Support"

    def test_all_have_error_message(self) -> None:
        for inc in _connector().fetch_incidents():
            assert inc.error_message, f"{inc.number} has empty error_message"

    def test_all_have_stack_trace(self) -> None:
        for inc in _connector().fetch_incidents():
            assert inc.stack_trace, f"{inc.number} has empty stack_trace"

    def test_covers_hl7_orm(self) -> None:
        subcats = {inc.subcategory for inc in _connector().fetch_incidents()}
        assert "HL7 ORM" in subcats

    def test_covers_hl7_oru(self) -> None:
        subcats = {inc.subcategory for inc in _connector().fetch_incidents()}
        assert "HL7 ORU" in subcats

    def test_covers_oauth_token(self) -> None:
        subcats = {inc.subcategory for inc in _connector().fetch_incidents()}
        assert "OAuth Token" in subcats

    def test_covers_dataweave(self) -> None:
        subcats = {inc.subcategory for inc in _connector().fetch_incidents()}
        assert "DataWeave" in subcats

    def test_covers_cloudhub(self) -> None:
        subcats = {inc.subcategory for inc in _connector().fetch_incidents()}
        assert "CloudHub" in subcats

    def test_phi_masking_applied_to_error_message(self) -> None:
        # Fixture contains no real PHI, but we verify masking runs by injecting
        # a temp fixture with a known PHI token.
        tmp_data = [
            {
                "sys_id": "x",
                "number": "INC9999999",
                "short_description": "test",
                "description": "",
                "assignment_group": "MuleSoft Support",
                "category": "Integration",
                "subcategory": "HL7 ORM",
                "priority": "2 - High",
                "state": "Resolved",
                "service_name": "svc",
                "environment": "production",
                "error_message": "Patient MRN-000001 caused failure",
                "stack_trace": "at Foo.bar(Foo.java:1)",
                "resolution_notes": "",
                "resolved_at": "",
                "tags": [],
            }
        ]
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(tmp_data, f)
            tmp_path = f.name
        try:
            incidents = ServiceNowConnector(fixture_path=tmp_path).fetch_incidents()
            assert "[MRN]" in incidents[0].error_message
            assert "MRN-000001" not in incidents[0].error_message
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# ServiceNowConnector — to_documents()
# ---------------------------------------------------------------------------


class TestToDocuments:
    def test_returns_ten_documents(self) -> None:
        docs = _connector().to_documents()
        assert len(docs) == 10

    def test_all_source_is_servicenow(self) -> None:
        for doc in _connector().to_documents():
            assert doc.source == "servicenow", f"Expected 'servicenow', got '{doc.source}'"

    def test_all_content_non_empty(self) -> None:
        for doc in _connector().to_documents():
            assert doc.content.strip(), f"Empty content for doc {doc.metadata.get('number')}"

    def test_metadata_has_required_keys(self) -> None:
        for doc in _connector().to_documents():
            for key in ("number", "description", "severity", "service", "source_system"):
                assert key in doc.metadata, f"Missing key '{key}' in {doc.metadata.get('number')}"

    def test_source_system_metadata_is_servicenow(self) -> None:
        for doc in _connector().to_documents():
            assert doc.metadata["source_system"] == "servicenow"

    def test_severity_values_are_valid(self) -> None:
        valid = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        for doc in _connector().to_documents():
            assert doc.metadata["severity"] in valid, (
                f"Invalid severity '{doc.metadata['severity']}' in {doc.metadata.get('number')}"
            )

    def test_documents_are_document_instances(self) -> None:
        for doc in _connector().to_documents():
            assert isinstance(doc, Document)

    def test_content_contains_error_message_keywords(self) -> None:
        docs = _connector().to_documents()
        # At least one doc should contain HL7-related terms
        hl7_docs = [
            d for d in docs if "HL7" in d.content or "ORM" in d.content or "ORU" in d.content
        ]
        assert hl7_docs, "No HL7-related content found in documents"

    def test_resolution_notes_in_content(self) -> None:
        docs = _connector().to_documents()
        # Resolution notes are part of content — check at least one has them
        resolved_docs = [
            d for d in docs if "null" in d.content.lower() or "timeout" in d.content.lower()
        ]
        assert resolved_docs

    def test_custom_fixture_path(self) -> None:
        import os
        import tempfile

        data = [
            {
                "sys_id": "t1",
                "number": "INC0000001",
                "short_description": "Test incident",
                "description": "desc",
                "assignment_group": "MuleSoft Support",
                "category": "Integration",
                "subcategory": "HL7 ORM",
                "priority": "3 - Medium",
                "state": "Resolved",
                "service_name": "test-svc",
                "environment": "production",
                "error_message": "Test error",
                "stack_trace": "at Test.run(Test.java:1)",
                "resolution_notes": "Fixed",
                "resolved_at": "2026-04-01T00:00:00Z",
                "tags": ["test"],
            }
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp_path = f.name
        try:
            docs = ServiceNowConnector(fixture_path=tmp_path).to_documents()
            assert len(docs) == 1
            assert docs[0].source == "servicenow"
            assert docs[0].metadata["number"] == "INC0000001"
        finally:
            os.unlink(tmp_path)
