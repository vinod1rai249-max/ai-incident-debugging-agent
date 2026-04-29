"""Pure-Python TF-IDF retriever — no scikit-learn, no faiss, no sentence-transformers."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import TYPE_CHECKING

from genai.rag.retrieval.base import BaseRetriever, Document

if TYPE_CHECKING:
    pass


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _tf(tokens: list[str]) -> dict[str, float]:
    counts = Counter(tokens)
    total = len(tokens) or 1
    return {term: count / total for term, count in counts.items()}


def _idf(term: str, corpus_tfs: list[dict[str, float]]) -> float:
    df = sum(1 for doc_tf in corpus_tfs if term in doc_tf)
    return math.log((len(corpus_tfs) + 1) / (df + 1)) + 1.0


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    shared = set(a) & set(b)
    if not shared:
        return 0.0
    dot = sum(a[t] * b[t] for t in shared)
    mag_a = math.sqrt(sum(v * v for v in a.values()))
    mag_b = math.sqrt(sum(v * v for v in b.values()))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class TFIDFRetriever(BaseRetriever):
    """In-memory TF-IDF retriever seeded from a list of Documents."""

    def __init__(self) -> None:
        self._docs: list[Document] = []
        self._tfidf_vecs: list[dict[str, float]] = []
        self._corpus_tfs: list[dict[str, float]] = []
        self._vocab: set[str] = set()

    # ------------------------------------------------------------------

    async def add_documents(self, documents: list[Document]) -> None:
        self._docs.extend(documents)
        self._corpus_tfs = [_tf(_tokenize(d.content)) for d in self._docs]
        self._vocab = {term for doc_tf in self._corpus_tfs for term in doc_tf}
        self._tfidf_vecs = [
            {term: tf_val * _idf(term, self._corpus_tfs) for term, tf_val in doc_tf.items()}
            for doc_tf in self._corpus_tfs
        ]

    async def retrieve(self, query: str, *, top_k: int = 3) -> list[Document]:
        if not self._docs:
            return []
        query_tf = _tf(_tokenize(query))
        query_tfidf = {
            term: tf_val * _idf(term, self._corpus_tfs) for term, tf_val in query_tf.items()
        }
        scored = [(i, _cosine(query_tfidf, doc_vec)) for i, doc_vec in enumerate(self._tfidf_vecs)]
        scored.sort(key=lambda x: x[1], reverse=True)
        results: list[Document] = []
        for idx, score in scored[:top_k]:
            doc = self._docs[idx].model_copy()
            doc = Document(
                content=doc.content,
                source=doc.source,
                metadata=doc.metadata,
                score=round(score, 4),
            )
            results.append(doc)
        return results
