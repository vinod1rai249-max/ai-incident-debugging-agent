from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from agents.incident.base import IncidentBaseAgent
from apps.incident_debugger.models import (
    AgentStepTrace,
    FixResult,
    IncidentInput,
    RootCauseResult,
)
from genai.prompts.base import BasePrompt
from genai.prompts.incident.fix_prompt import FixPrompt


class FixAgent(IncidentBaseAgent):
    name = "FixAgent"
    max_output_tokens = 700
    temperature = 0.1

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._prompt = FixPrompt()

    @property
    def prompt(self) -> BasePrompt:
        return self._prompt

    def output_schema(self) -> type[BaseModel]:
        return FixResult

    def _build_context(self, **kwargs: Any) -> dict[str, str]:
        incident: IncidentInput = kwargs["incident"]
        root_cause: RootCauseResult = kwargs["root_cause"]
        return {
            "service_name": incident.service_name or "unknown",
            "environment": incident.environment,
            "error_message": incident.error_message,
            "root_cause": root_cause.root_cause,
            "contributing_factors": ", ".join(root_cause.contributing_factors),
            "affected_components": ", ".join(root_cause.affected_components),
        }

    async def run(  # type: ignore[override]
        self, *, incident: IncidentInput, root_cause: RootCauseResult
    ) -> tuple[FixResult, AgentStepTrace]:
        output, trace = await super().run(incident=incident, root_cause=root_cause)
        return cast(FixResult, output), trace
