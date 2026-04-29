import pytest

from genai.rag.retrieval.base import Document


def test_document_defaults() -> None:
    doc = Document(content="hello", source="test.pdf")
    assert doc.metadata == {}
    assert doc.score == 0.0


def test_document_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Document(content="", source="test.pdf")


def test_document_rejects_whitespace_content() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        Document(content="   ", source="test.pdf")
