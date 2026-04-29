from abc import ABC, abstractmethod

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMResponse(BaseModel):
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    latency_ms: float


class BaseLLMClient(ABC):
    """Abstract contract for all LLM provider clients."""

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int,
        temperature: float,
        system: str = "",
    ) -> LLMResponse: ...

    @abstractmethod
    def model_name(self) -> str: ...
