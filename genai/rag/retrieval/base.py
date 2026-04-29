from abc import ABC, abstractmethod

from pydantic import BaseModel, field_validator


class Document(BaseModel):
    content: str
    source: str
    metadata: dict[str, str] = {}
    score: float = 0.0

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
        return v


class BaseRetriever(ABC):
    """Abstract contract for all vector store retrievers."""

    @abstractmethod
    async def retrieve(self, query: str, *, top_k: int) -> list[Document]: ...

    @abstractmethod
    async def add_documents(self, documents: list[Document]) -> None: ...
