from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from agents.validation.output_validator import validate_output
from apps.incident_debugger.models import AgentStepTrace
from core.circuit_breaker import CircuitBreaker, CircuitOpenError
from core.cost import TokenUsage
from core.exceptions import IncidentAnalysisError, LLMError, ValidationError
from core.logging import get_logger
from genai.clients.base import BaseLLMClient, LLMMessage
from genai.prompts.base import BasePrompt

logger = get_logger(__name__)


def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers LLMs sometimes add."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        return "\n".join(inner).strip()
    return stripped


def _repair_truncated_json(raw: str) -> str:
    """Attempt to close truncated JSON caused by hitting a token limit.

    Walks the string tracking open braces/brackets and string state, then
    appends the minimum suffix needed to produce syntactically valid JSON.
    Only closes structure — it does not fabricate missing values.
    """
    s = raw.rstrip()
    in_string = False
    escape_next = False
    stack: list[str] = []  # expected closing chars in order

    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ("{", "["):
            stack.append("}" if ch == "{" else "]")
        elif ch in ("}", "]") and stack and stack[-1] == ch:
            stack.pop()

    if not in_string and not stack:
        return s  # already structurally complete

    candidate = s
    if in_string:
        candidate += '"'  # close the open string literal
    # Strip a trailing comma left before a truncated next element
    candidate = candidate.rstrip()
    if candidate.endswith(","):
        candidate = candidate[:-1]
    candidate += "".join(reversed(stack))
    return candidate


def _parse_json(raw: str) -> dict:
    """Parse JSON, attempting a structural repair if the first parse fails."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        repaired = _repair_truncated_json(raw)
        return json.loads(repaired)  # raises JSONDecodeError if repair also fails


class IncidentBaseAgent(ABC):
    """Single-shot LLM agent for incident analysis.

    Each subclass defines its name, token budget, prompt, output schema, and
    how to build the prompt context from caller-supplied keyword arguments.

    Handles:
    - Up to ``max_retries`` attempts with exponential back-off
    - JSON schema hint injected on retry attempts
    - Circuit breaker fast-fail (no retries when circuit is OPEN)
    - AgentStepTrace produced on both success and failure paths
    """

    name: ClassVar[str] = ""
    max_output_tokens: ClassVar[int] = 1024
    temperature: ClassVar[float] = 0.1

    def __init__(
        self,
        llm_client: BaseLLMClient,
        circuit_breaker: CircuitBreaker,
        max_retries: int = 3,
        base_wait_s: float = 1.0,
    ) -> None:
        self._llm = llm_client
        self._cb = circuit_breaker
        self._max_retries = max_retries
        self._base_wait_s = base_wait_s

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def prompt(self) -> BasePrompt: ...

    @abstractmethod
    def output_schema(self) -> type[BaseModel]: ...

    @abstractmethod
    def _build_context(self, **kwargs: Any) -> dict[str, str]: ...

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(self, **kwargs: Any) -> tuple[BaseModel, AgentStepTrace]:
        start = time.monotonic()
        model_id = self._llm.model_name()
        last_exc: Exception | None = None
        last_response = None

        for attempt in range(1, self._max_retries + 1):
            try:
                context = self._build_context(**kwargs)
                system, user = self.prompt.render(**context)

                # On retries inject the JSON schema so the LLM knows exactly what to return
                if attempt > 1:
                    schema_json = json.dumps(self.output_schema().model_json_schema(), indent=2)
                    user = (
                        f"{user}\n\n"
                        f"Your previous response could not be parsed. "
                        f"Respond with ONLY valid JSON matching this schema:\n{schema_json}"
                    )

                logger.info("agent.start", agent=self.name, attempt=attempt, model=model_id)

                last_response = await self._cb.call(
                    self._llm.complete,
                    messages=[LLMMessage(role="user", content=user)],
                    max_tokens=self.max_output_tokens,
                    temperature=self.temperature,
                    system=system,
                )

                raw = _strip_code_fence(last_response.content)
                parsed = _parse_json(raw)
                output = validate_output(parsed, self.output_schema(), context=self.name)

                latency_ms = (time.monotonic() - start) * 1000
                usage = TokenUsage(
                    model=model_id,
                    input_tokens=last_response.input_tokens,
                    output_tokens=last_response.output_tokens,
                    cached_tokens=last_response.cached_tokens,
                )
                trace = AgentStepTrace(
                    agent_name=self.name,
                    model_id=model_id,
                    status="success",
                    latency_ms=round(latency_ms, 2),
                    input_tokens=last_response.input_tokens,
                    output_tokens=last_response.output_tokens,
                    cost_usd=round(usage.cost_usd, 6),
                )
                logger.info(
                    "agent.complete",
                    agent=self.name,
                    latency_ms=round(latency_ms, 1),
                    cost_usd=round(usage.cost_usd, 6),
                )
                return output, trace

            except CircuitOpenError as exc:
                last_exc = exc
                logger.warning("agent.circuit_open", agent=self.name)
                break  # no point retrying — circuit is open

            except (json.JSONDecodeError, ValidationError, LLMError) as exc:
                last_exc = exc
                logger.warning(
                    "agent.retry",
                    agent=self.name,
                    attempt=attempt,
                    max=self._max_retries,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    wait = min(self._base_wait_s * (2 ** (attempt - 1)), 10.0)
                    await asyncio.sleep(wait)

        # All attempts exhausted or circuit open
        latency_ms = (time.monotonic() - start) * 1000
        trace = AgentStepTrace(
            agent_name=self.name,
            model_id=model_id,
            status="error",
            latency_ms=round(latency_ms, 2),
            input_tokens=last_response.input_tokens if last_response else 0,
            output_tokens=last_response.output_tokens if last_response else 0,
            cost_usd=0.0,
            error=str(last_exc),
        )
        logger.error(
            "agent.failed",
            agent=self.name,
            attempts=self._max_retries,
            error=str(last_exc),
        )
        raise IncidentAnalysisError(
            f"{self.name} failed after {self._max_retries} attempt(s): {last_exc}"
        ) from last_exc
