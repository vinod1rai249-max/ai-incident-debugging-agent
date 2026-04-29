from agents.tools.base import BaseTool
from core.exceptions import ToolError
from core.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ToolError(f"Tool already registered: {tool.name}", tool_name=tool.name)
        self._tools[tool.name] = tool
        logger.info("tool_registered", tool=tool.name)

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"Tool not found: {name}", tool_name=name)
        return tool

    def all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
