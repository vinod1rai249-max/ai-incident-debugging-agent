from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from agents.incident.base import IncidentBaseAgent
from apps.incident_debugger.models import AgentStepTrace, IncidentInput, PlannerResult, TriageResult
from genai.prompts.base import BasePrompt
from genai.prompts.incident.classifier_prompt import ClassifierPrompt


class ClassifierAgent(IncidentBaseAgent):
    name = "ClassifierAgent"
    max_output_tokens = 300
    temperature = 0.1

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._prompt = ClassifierPrompt()

    @property
    def prompt(self) -> BasePrompt:
        return self._prompt

    def output_schema(self) -> type[BaseModel]:
        return TriageResult

    def _build_context(self, **kwargs: Any) -> dict[str, str]:
        incident: IncidentInput = kwargs["incident"]
        planner: PlannerResult = kwargs["planner"]
        code_block = f"\nCode Snippet:\n{incident.code_snippet}" if incident.code_snippet else ""
        return {
            "service_name": incident.service_name or "unknown",
            "environment": incident.environment,
            "error_message": incident.error_message,
            "stack_trace": incident.stack_trace,
            "logs": incident.logs,
            "code_block": code_block,
            "analysis_plan": "\n".join(f"- {s}" for s in planner.steps),
        }

    async def run(  # type: ignore[override]
        self, *, incident: IncidentInput, planner: PlannerResult
    ) -> tuple[TriageResult, AgentStepTrace]:
        output, trace = await super().run(incident=incident, planner=planner)
        return cast(TriageResult, output), trace
