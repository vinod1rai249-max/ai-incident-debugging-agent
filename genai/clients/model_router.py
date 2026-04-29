from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from core.exceptions import AppError
from core.logging import get_logger

logger = get_logger(__name__)


class TaskType(StrEnum):
    FAST = "fast"  # low-latency: classification, routing, short answers
    STANDARD = "standard"  # general-purpose: summarisation, QA, RAG generation
    COMPLEX = "complex"  # multi-step reasoning, agentic planning, long-form synthesis


class ModelProfile(BaseModel):
    model_id: str
    provider: str  # "anthropic" | "openai"
    max_tokens: int = Field(gt=0)
    temperature: float = Field(ge=0.0, le=2.0, default=0.2)
    supports_caching: bool = False

    @model_validator(mode="after")
    def _provider_must_be_known(self) -> "ModelProfile":
        if self.provider not in {"anthropic", "openai"}:
            raise ValueError(f"Unknown provider: {self.provider}")
        return self


# Default routing table — override by passing a custom table to ModelRouter.__init__
DEFAULT_ROUTING_TABLE: dict[TaskType, ModelProfile] = {
    TaskType.FAST: ModelProfile(
        model_id="claude-haiku-4-5-20251001",
        provider="anthropic",
        max_tokens=1024,
        temperature=0.1,
        supports_caching=True,
    ),
    TaskType.STANDARD: ModelProfile(
        model_id="claude-sonnet-4-6",
        provider="anthropic",
        max_tokens=4096,
        temperature=0.2,
        supports_caching=True,
    ),
    TaskType.COMPLEX: ModelProfile(
        model_id="claude-opus-4-7",
        provider="anthropic",
        max_tokens=8192,
        temperature=0.3,
        supports_caching=True,
    ),
}


class ModelRouter:
    """Routes a task type to the appropriate ModelProfile.

    Keeps routing logic out of business code and makes it
    easy to swap models without touching call sites.
    """

    def __init__(
        self,
        routing_table: dict[TaskType, ModelProfile] | None = None,
        fallback: TaskType = TaskType.STANDARD,
    ) -> None:
        self._table = DEFAULT_ROUTING_TABLE if routing_table is None else routing_table
        self._fallback = fallback
        self._validate_table()

    def get_model(self, task_type: TaskType) -> ModelProfile:
        profile = self._table.get(task_type)
        if profile is None:
            logger.warning(
                "unknown_task_type_using_fallback",
                requested=task_type,
                fallback=self._fallback,
            )
            profile = self._table[self._fallback]
        logger.debug("model_routed", task_type=task_type, model_id=profile.model_id)
        return profile

    def register(self, task_type: TaskType, profile: ModelProfile) -> None:
        """Add or replace a route at runtime (e.g. for A/B testing or env overrides)."""
        self._table[task_type] = profile
        logger.info("model_route_registered", task_type=task_type, model_id=profile.model_id)

    def available_task_types(self) -> list[TaskType]:
        return list(self._table.keys())

    def _validate_table(self) -> None:
        if self._fallback not in self._table:
            raise AppError(
                f"ROUTER_CONFIG_ERROR: fallback '{self._fallback}' has no entry in routing table.",
                code="ROUTER_CONFIG_ERROR",
            )
