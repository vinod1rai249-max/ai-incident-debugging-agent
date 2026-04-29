import pytest

from core.exceptions import AppError
from genai.clients.model_router import (
    DEFAULT_ROUTING_TABLE,
    ModelProfile,
    ModelRouter,
    TaskType,
)


@pytest.fixture()
def router() -> ModelRouter:
    return ModelRouter()


def test_routes_fast_to_haiku(router: ModelRouter) -> None:
    profile = router.get_model(TaskType.FAST)
    assert "haiku" in profile.model_id


def test_routes_complex_to_opus(router: ModelRouter) -> None:
    profile = router.get_model(TaskType.COMPLEX)
    assert "opus" in profile.model_id


def test_routes_standard_to_sonnet(router: ModelRouter) -> None:
    profile = router.get_model(TaskType.STANDARD)
    assert "sonnet" in profile.model_id


def test_fallback_used_when_task_type_missing() -> None:
    partial_table = {TaskType.STANDARD: DEFAULT_ROUTING_TABLE[TaskType.STANDARD]}
    router = ModelRouter(routing_table=partial_table, fallback=TaskType.STANDARD)
    profile = router.get_model(TaskType.FAST)  # FAST not in table → fallback
    assert "sonnet" in profile.model_id


def test_invalid_fallback_raises_on_init() -> None:
    with pytest.raises(AppError, match="ROUTER_CONFIG_ERROR"):
        ModelRouter(routing_table={}, fallback=TaskType.STANDARD)


def test_register_overrides_route(router: ModelRouter) -> None:
    custom = ModelProfile(model_id="gpt-4o-mini", provider="openai", max_tokens=512)
    router.register(TaskType.FAST, custom)
    assert router.get_model(TaskType.FAST).model_id == "gpt-4o-mini"


def test_model_profile_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        ModelProfile(model_id="some-model", provider="google", max_tokens=1024)


def test_model_profile_rejects_zero_max_tokens() -> None:
    with pytest.raises(ValueError):
        ModelProfile(model_id="x", provider="anthropic", max_tokens=0)


def test_available_task_types_matches_table(router: ModelRouter) -> None:
    assert set(router.available_task_types()) == set(DEFAULT_ROUTING_TABLE.keys())
