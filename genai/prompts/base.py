from abc import ABC, abstractmethod
from string import Template


class BasePrompt(ABC):
    """Versioned, testable prompt template. Subclass per use case."""

    version: str = "1.0"

    @property
    @abstractmethod
    def system(self) -> str:
        """Static system instruction — suitable for prompt caching."""
        ...

    @abstractmethod
    def user(self, **kwargs: str) -> str:
        """Render the user turn with runtime variables."""
        ...

    def render(self, **kwargs: str) -> tuple[str, str]:
        """Return (system, user) ready to pass to BaseLLMClient.complete()."""
        return self.system, self.user(**kwargs)

    @classmethod
    def _fill(cls, template: str, **kwargs: str) -> str:
        return Template(template).substitute(**kwargs)
