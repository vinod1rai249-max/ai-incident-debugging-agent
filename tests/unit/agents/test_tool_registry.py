import pytest
from pydantic import BaseModel

from agents.tools.base import BaseTool
from agents.tools.registry import ToolRegistry
from core.exceptions import ToolError


class _Input(BaseModel):
    query: str


class _Output(BaseModel):
    result: str


class _FakeTool(BaseTool):
    @property
    def name(self) -> str:
        return "fake_tool"

    @property
    def description(self) -> str:
        return "A fake tool for testing."

    @property
    def input_schema(self) -> type[BaseModel]:
        return _Input

    @property
    def output_schema(self) -> type[BaseModel]:
        return _Output

    async def execute(self, inputs: BaseModel) -> BaseModel:
        assert isinstance(inputs, _Input)
        return _Output(result=f"got: {inputs.query}")


@pytest.fixture()
def registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture()
def tool() -> _FakeTool:
    return _FakeTool()


def test_register_and_get(registry: ToolRegistry, tool: _FakeTool) -> None:
    registry.register(tool)
    assert registry.get("fake_tool") is tool


def test_get_unknown_raises(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError, match="Tool not found: missing"):
        registry.get("missing")


def test_duplicate_register_raises(registry: ToolRegistry, tool: _FakeTool) -> None:
    registry.register(tool)
    with pytest.raises(ToolError, match="already registered"):
        registry.register(tool)


def test_contains(registry: ToolRegistry, tool: _FakeTool) -> None:
    assert "fake_tool" not in registry
    registry.register(tool)
    assert "fake_tool" in registry


def test_names_and_all(registry: ToolRegistry, tool: _FakeTool) -> None:
    registry.register(tool)
    assert registry.names() == ["fake_tool"]
    assert registry.all() == [tool]
    assert len(registry) == 1
