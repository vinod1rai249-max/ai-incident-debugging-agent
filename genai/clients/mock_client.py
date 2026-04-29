from collections import deque

from genai.clients.base import BaseLLMClient, LLMMessage, LLMResponse


class MockLLMClient(BaseLLMClient):
    """Deterministic LLM client for tests — returns canned responses in order.

    Pass a list of JSON strings to responses; each call pops the first one.
    If the list is exhausted the last response is repeated, so a single-item
    list acts as a constant stub.
    """

    def __init__(
        self,
        responses: list[str],
        model: str = "claude-sonnet-4-6",
        input_tokens: int = 100,
        output_tokens: int = 50,
    ) -> None:
        if not responses:
            raise ValueError("MockLLMClient requires at least one response string")
        self._responses: deque[str] = deque(responses)
        self._model = model
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int,
        temperature: float,
        system: str = "",
    ) -> LLMResponse:
        content = self._responses[0] if len(self._responses) == 1 else self._responses.popleft()
        return LLMResponse(
            content=content,
            model=self._model,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            cached_tokens=0,
            latency_ms=1.0,
        )

    def model_name(self) -> str:
        return self._model
