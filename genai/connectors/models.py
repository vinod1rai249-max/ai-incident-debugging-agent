"""Shared connector models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ObservabilityEvent(BaseModel):
    """A single observability event emitted by an APM tool (e.g. Dynatrace).

    Fields mirror the Dynatrace log ingest schema but are generic enough to
    represent events from any structured log source.
    """

    event_id: str = Field(..., description="Unique event / log-entry identifier")
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp")
    level: Literal["ERROR", "WARN", "INFO", "DEBUG"] = Field(..., description="Log severity level")
    service_name: str = Field(..., description="Originating service or application name")
    host: str = Field(default="", description="Host or CloudHub worker that emitted the event")
    environment: str = Field(default="production", description="Deployment environment")
    trace_id: str = Field(default="", description="Distributed trace identifier")
    span_id: str = Field(default="", description="Span identifier within the trace")
    message: str = Field(..., description="Human-readable log message (PHI-masked)")
    error_type: str = Field(default="", description="Fully-qualified exception class name")
    stack_trace: str = Field(default="", description="Stack trace text (PHI-masked)")
    tags: list[str] = Field(default_factory=list, description="Searchable tag list")

    @property
    def severity(self) -> str:
        """Map log level to a normalised severity label used in retriever metadata."""
        return {"ERROR": "HIGH", "WARN": "MEDIUM", "INFO": "LOW", "DEBUG": "LOW"}.get(
            self.level, "MEDIUM"
        )
