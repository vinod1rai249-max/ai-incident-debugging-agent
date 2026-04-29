from genai.prompts.base import BasePrompt

_SYSTEM = """\
You are a precise question-answering assistant.
Answer ONLY using the provided context. If the context does not contain enough
information to answer, say "I don't know" — do not speculate.
Cite the source of each claim using [source] notation."""

_USER = """\
Context:
$context

Question: $question

Answer:"""


class RAGPrompt(BasePrompt):
    version = "1.0"

    @property
    def system(self) -> str:
        return _SYSTEM

    def user(self, *, context: str, question: str, **_: str) -> str:  # type: ignore[override]
        return self._fill(_USER, context=context, question=question)
