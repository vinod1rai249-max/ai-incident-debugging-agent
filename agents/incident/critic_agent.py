from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from agents.incident.base import IncidentBaseAgent
from apps.incident_debugger.models import (
    AgentStepTrace,
    CriticResult,
    FixResult,
    IncidentInput,
    RootCauseResult,
)
from genai.prompts.base import BasePrompt
from genai.prompts.incident.critic_prompt import CriticPrompt


class CriticAgent(IncidentBaseAgent):
    name = "CriticAgent"
    max_output_tokens = 300
    temperature = 0.1

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._prompt = CriticPrompt()

    @property
    def prompt(self) -> BasePrompt:
        return self._prompt

    def output_schema(self) -> type[BaseModel]:
        return CriticResult

    def _build_context(self, **kwargs: Any) -> dict[str, str]:
        incident: IncidentInput = kwargs["incident"]
        root_cause: RootCauseResult = kwargs["root_cause"]
        fix: FixResult = kwargs["fix"]
        return {
            "service_name": incident.service_name or "unknown",
            "error_message": incident.error_message,
            "root_cause": root_cause.root_cause,
            "contributing_factors": ", ".join(root_cause.contributing_factors),
            "quick_fix": fix.quick_fix,
            "long_term_fix": fix.long_term_fix,
            "validation_steps": "\n".join(f"- {s}" for s in fix.validation_steps),
            "rollback_plan": fix.rollback_plan,
        }

    async def run(  # type: ignore[override]
        self,
        *,
        incident: IncidentInput,
        root_cause: RootCauseResult,
        fix: FixResult,
    ) -> tuple[CriticResult, AgentStepTrace]:
        output, trace = await super().run(incident=incident, root_cause=root_cause, fix=fix)
        return cast(CriticResult, output), trace
