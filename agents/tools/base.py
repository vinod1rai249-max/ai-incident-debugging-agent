from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def input_schema(self) -> type[BaseModel]: ...

    @property
    @abstractmethod
    def output_schema(self) -> type[BaseModel]: ...

    @abstractmethod
    async def execute(self, inputs: BaseModel) -> BaseModel: ...

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_json_schema(),
        }
