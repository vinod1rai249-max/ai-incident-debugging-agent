import time
from typing import Literal, cast

import anthropic

from core.config import settings
from core.cost import CostAccumulator, TokenUsage
from core.exceptions import LLMError
from core.logging import get_logger
from core.retry import build_retry
from genai.clients.base import BaseLLMClient, LLMMessage, LLMResponse

logger = get_logger(__name__)

MODEL_NAME = settings.model_name


class AnthropicClient(BaseLLMClient):
    def __init__(self, model: str = MODEL_NAME) -> None:
        self._model = model
        self.cost = CostAccumulator()
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._retry = build_retry(reraise_types=(LLMError,))

    def model_name(self) -> str:
        return self._model

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int,
        temperature: float,
        system: str = "",
    ) -> LLMResponse:
        async for attempt in self._retry:
            with attempt:
                start = time.monotonic()
                try:
                    api_messages: list[dict[str, str]] = [
                        {
                            "role": m.role if m.role in ("user", "assistant") else "user",
                            "content": m.content,
                        }
                        for m in messages
                    ]
                    response = await self._client.messages.create(
                        model=self._model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system,
                        messages=[
                            {
                                "role": cast(Literal["user", "assistant"], msg["role"]),
                                "content": msg["content"],
                            }
                            for msg in api_messages
                        ],
                    )
                except anthropic.APIError as exc:
                    raise LLMError(str(exc)) from exc

                latency_ms = (time.monotonic() - start) * 1000
                usage = response.usage
                cached = getattr(usage, "cache_read_input_tokens", 0) or 0

                text_block = next(
                    (b for b in response.content if isinstance(b, anthropic.types.TextBlock)),
                    None,
                )
                if text_block is None:
                    raise LLMError("LLM response contained no text block")
                result = LLMResponse(
                    content=text_block.text,
                    model=self._model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cached_tokens=cached,
                    latency_ms=latency_ms,
                )
                usage_record = TokenUsage(
                    model=self._model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cached_tokens=result.cached_tokens,
                )
                self.cost.add(usage_record)
                logger.info(
                    "llm_call_complete",
                    model=self._model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cached_tokens=result.cached_tokens,
                    latency_ms=round(latency_ms, 1),
                    cost_usd=round(usage_record.cost_usd, 6),
                )
                return result

        raise LLMError("Exhausted retries")  # unreachable but satisfies mypy
