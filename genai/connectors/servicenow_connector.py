"""Mock ServiceNow connector — reads from a local JSON fixture.

No real ServiceNow API calls are made.  The connector loads incidents from
``data/servicenow_mulesoft_healthcare_incidents.json`` (relative to the
project root), applies PHI masking, and converts each record to a
``Document`` ready for the TF-IDF retriever.

Source label on every returned document: ``"servicenow"``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.phi_masker import mask_phi
from genai.rag.retrieval.base import Document

_DEFAULT_FIXTURE: Path = (
    Path(__file__).parent.parent.parent / "data" / "servicenow_mulesoft_healthcare_incidents.json"
)

# ServiceNow priority string → normalised severity label
_PRIORITY_MAP: dict[str, str] = {
    "1 - Critical": "CRITICAL",
    "2 - High": "HIGH",
    "3 - Medium": "MEDIUM",
    "4 - Low": "LOW",
}


class ServiceNowIncident:
    """Lightweight value object representing one ServiceNow incident record."""

    __slots__ = (
        "sys_id",
        "number",
        "short_description",
        "description",
        "assignment_group",
        "category",
        "subcategory",
        "priority",
        "state",
        "service_name",
        "environment",
        "error_message",
        "stack_trace",
        "resolution_notes",
        "resolved_at",
        "tags",
    )

    def __init__(self, raw: dict[str, Any]) -> None:
        self.sys_id: str = raw.get("sys_id", "")
        self.number: str = raw.get("number", "")
        self.short_description: str = raw.get("short_description", "")
        self.description: str = raw.get("description", "")
        self.assignment_group: str = raw.get("assignment_group", "")
        self.category: str = raw.get("category", "")
        self.subcategory: str = raw.get("subcategory", "")
        self.priority: str = raw.get("priority", "")
        self.state: str = raw.get("state", "")
        self.service_name: str = raw.get("service_name", "")
        self.environment: str = raw.get("environment", "")
        self.error_message: str = raw.get("error_message", "")
        self.stack_trace: str = raw.get("stack_trace", "")
        self.resolution_notes: str = raw.get("resolution_notes", "")
        self.resolved_at: str = raw.get("resolved_at", "")
        self.tags: list[str] = raw.get("tags", [])

    @property
    def severity(self) -> str:
        return _PRIORITY_MAP.get(self.priority, "MEDIUM")


class ServiceNowConnector:
    """Mock connector that loads ServiceNow incidents from a local JSON fixture.

    Parameters
    ----------
    fixture_path:
        Path to the JSON fixture file.  Defaults to
        ``data/servicenow_mulesoft_healthcare_incidents.json`` at the project
        root.  Override in tests to point at a smaller fixture.
    """

    def __init__(self, fixture_path: str | Path | None = None) -> None:
        self._path = Path(fixture_path) if fixture_path else _DEFAULT_FIXTURE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_incidents(self) -> list[ServiceNowIncident]:
        """Load and return all incidents from the fixture (PHI masked)."""
        raw_list: list[dict[str, Any]] = json.loads(self._path.read_text(encoding="utf-8"))
        return [ServiceNowIncident(self._mask_record(r)) for r in raw_list]

    def to_documents(self) -> list[Document]:
        """Convert all incidents to ``Document`` objects for the retriever.

        Each document's ``source`` is set to ``"servicenow"`` so callers can
        distinguish it from other corpus sources (e.g. Dynatrace).
        """
        return [self._incident_to_document(inc) for inc in self.fetch_incidents()]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mask_record(raw: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of *raw* with PHI/secret fields masked."""
        text_fields = (
            "short_description",
            "description",
            "error_message",
            "stack_trace",
            "resolution_notes",
        )
        masked = dict(raw)
        for field in text_fields:
            if isinstance(masked.get(field), str):
                masked[field] = mask_phi(masked[field])
        return masked

    @staticmethod
    def _incident_to_document(inc: ServiceNowIncident) -> Document:
        content = " ".join(
            filter(
                None,
                [
                    inc.short_description,
                    inc.error_message,
                    inc.stack_trace,
                    inc.resolution_notes,
                ],
            )
        )
        return Document(
            content=content,
            source="servicenow",
            metadata={
                "number": inc.number,
                "description": inc.short_description,
                "severity": inc.severity,
                "subcategory": inc.subcategory,
                "service": inc.service_name,
                "resolution": inc.resolution_notes,
                "source_system": "servicenow",
            },
        )
