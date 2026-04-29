"""Mock Dynatrace connector — reads from a local JSON fixture.

No real Dynatrace API calls are made.  The connector loads structured log
entries from ``data/dynatrace_mulesoft_logs.json``, applies PHI masking,
parses each entry into an ``ObservabilityEvent``, and converts the result
to ``Document`` objects ready for the TF-IDF retriever.

Source label on every returned document: ``"dynatrace"``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.phi_masker import mask_phi
from genai.connectors.models import ObservabilityEvent
from genai.rag.retrieval.base import Document

_DEFAULT_FIXTURE: Path = (
    Path(__file__).parent.parent.parent / "data" / "dynatrace_mulesoft_logs.json"
)


class DynatraceConnector:
    """Mock connector that loads Dynatrace log entries from a local JSON fixture.

    Parameters
    ----------
    fixture_path:
        Path to the JSON fixture file.  Defaults to
        ``data/dynatrace_mulesoft_logs.json`` at the project root.
        Override in tests to point at a smaller fixture.
    """

    def __init__(self, fixture_path: str | Path | None = None) -> None:
        self._path = Path(fixture_path) if fixture_path else _DEFAULT_FIXTURE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_events(self) -> list[ObservabilityEvent]:
        """Load, mask, and return all log entries as ``ObservabilityEvent`` objects."""
        raw_list: list[dict[str, Any]] = json.loads(self._path.read_text(encoding="utf-8"))
        return [ObservabilityEvent(**self._mask_record(r)) for r in raw_list]

    def to_documents(self) -> list[Document]:
        """Convert all log entries to ``Document`` objects for the retriever.

        Each document's ``source`` is set to ``"dynatrace"`` so callers can
        distinguish it from other corpus sources (e.g. ServiceNow).
        """
        return [self._event_to_document(ev) for ev in self.fetch_events()]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mask_record(raw: dict[str, Any]) -> dict[str, Any]:
        """Normalise field names and mask PHI/secrets in text fields."""
        masked = dict(raw)
        # Dynatrace fixture uses "log_id"; ObservabilityEvent expects "event_id"
        if "log_id" in masked and "event_id" not in masked:
            masked["event_id"] = masked.pop("log_id")
        text_fields = ("message", "stack_trace", "error_type")
        for field in text_fields:
            if isinstance(masked.get(field), str):
                masked[field] = mask_phi(masked[field])
        return masked

    @staticmethod
    def _event_to_document(event: ObservabilityEvent) -> Document:
        content = " ".join(
            filter(
                None,
                [
                    event.message,
                    event.error_type,
                    event.stack_trace,
                ],
            )
        )
        return Document(
            content=content,
            source="dynatrace",
            metadata={
                "log_id": event.event_id,
                "description": event.message,
                "severity": event.severity,
                "service": event.service_name,
                "level": event.level,
                "error_type": event.error_type,
                "source_system": "dynatrace",
            },
        )
