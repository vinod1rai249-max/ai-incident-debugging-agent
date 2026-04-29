from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from agents.incident.base import IncidentBaseAgent
from apps.incident_debugger.models import (
    AgentStepTrace,
    IncidentInput,
    RootCauseResult,
    TriageResult,
)
from genai.prompts.base import BasePrompt
from genai.prompts.incident.root_cause_prompt import RootCausePrompt


class RootCauseAgent(IncidentBaseAgent):
    name = "RootCauseAgent"
    max_output_tokens = 700
    temperature = 0.1

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._prompt = RootCausePrompt()

    @property
    def prompt(self) -> BasePrompt:
        return self._prompt

    def output_schema(self) -> type[BaseModel]:
        return RootCauseResult

    def _build_context(self, **kwargs: Any) -> dict[str, str]:
        incident: IncidentInput = kwargs["incident"]
        classifier: TriageResult = kwargs["classifier"]
        rag_context: str = kwargs.get("rag_context", "")
        code_block = f"\nCode Snippet:\n{incident.code_snippet}" if incident.code_snippet else ""
        rag_section = (
            "\nSimilar Past Incidents (RAG)\n"
            "============================\n"
            f"{rag_context}\n\n"
            "Compare each incident above against the current error.\n"
            "In root_cause, reference the closest matching incident by [index]"
            " only if directly applicable.\n"
            "Adapt any relevant pattern — do not copy a past fix verbatim."
            if rag_context
            else ""
        )
        return {
            "service_name": incident.service_name or "unknown",
            "environment": incident.environment,
            "error_message": incident.error_message,
            "stack_trace": incident.stack_trace,
            "logs": incident.logs,
            "code_block": code_block,
            "error_category": classifier.error_category,
            "key_signals": ", ".join(classifier.key_signals),
            "rag_context": rag_section,
        }

    async def run(  # type: ignore[override]
        self,
        *,
        incident: IncidentInput,
        classifier: TriageResult,
        rag_context: str = "",
    ) -> tuple[RootCauseResult, AgentStepTrace]:
        output, trace = await super().run(
            incident=incident, classifier=classifier, rag_context=rag_context
        )
        return cast(RootCauseResult, output), trace
