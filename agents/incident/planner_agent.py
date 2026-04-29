from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from agents.incident.base import IncidentBaseAgent
from apps.incident_debugger.models import AgentStepTrace, IncidentInput, PlannerResult
from genai.prompts.base import BasePrompt
from genai.prompts.incident.planner_prompt import PlannerPrompt


class PlannerAgent(IncidentBaseAgent):
    name = "PlannerAgent"
    max_output_tokens = 1024
    temperature = 0.1

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._prompt = PlannerPrompt()

    @property
    def prompt(self) -> BasePrompt:
        return self._prompt

    def output_schema(self) -> type[BaseModel]:
        return PlannerResult

    def _build_context(self, **kwargs: Any) -> dict[str, str]:
        incident: IncidentInput = kwargs["incident"]
        code_block = f"\nCode Snippet:\n{incident.code_snippet}" if incident.code_snippet else ""
        return {
            "service_name": incident.service_name or "unknown",
            "environment": incident.environment,
            "error_message": incident.error_message,
            "stack_trace": incident.stack_trace,
            "logs": incident.logs,
            "code_block": code_block,
        }

    async def run(  # type: ignore[override]
        self, *, incident: IncidentInput
    ) -> tuple[PlannerResult, AgentStepTrace]:
        output, trace = await super().run(incident=incident)
        return cast(PlannerResult, output), trace
