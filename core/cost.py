from dataclasses import dataclass, field

from core.logging import get_logger

logger = get_logger(__name__)

# Price per 1M tokens in USD — update as providers change pricing
_PRICE_PER_M_TOKENS: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30},
    "claude-opus-4-7": {"input": 15.00, "output": 75.00, "cache_read": 1.50},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00, "cache_read": 0.08},
    "gpt-4o": {"input": 5.00, "output": 15.00, "cache_read": 2.50},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cache_read": 0.075},
}


@dataclass
class TokenUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        prices = _PRICE_PER_M_TOKENS.get(self.model)
        if prices is None:
            logger.warning("unknown_model_pricing", model=self.model)
            return 0.0
        billable_input = max(0, self.input_tokens - self.cached_tokens)
        return (
            billable_input * prices["input"]
            + self.cached_tokens * prices["cache_read"]
            + self.output_tokens * prices["output"]
        ) / 1_000_000


@dataclass
class CostAccumulator:
    """Accumulate token usage and cost across multiple LLM calls in one run."""

    _entries: list[TokenUsage] = field(default_factory=list)

    def add(self, usage: TokenUsage) -> None:
        self._entries.append(usage)
        logger.debug(
            "token_usage",
            model=usage.model,
            input=usage.input_tokens,
            output=usage.output_tokens,
            cached=usage.cached_tokens,
            cost_usd=round(usage.cost_usd, 6),
        )

    @property
    def total_cost_usd(self) -> float:
        return sum(e.cost_usd for e in self._entries)

    @property
    def total_input_tokens(self) -> int:
        return sum(e.input_tokens for e in self._entries)

    @property
    def total_output_tokens(self) -> int:
        return sum(e.output_tokens for e in self._entries)

    def summary(self) -> dict[str, object]:
        return {
            "calls": len(self._entries),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
        }
