"""Build MockLLMClient instances with responses matched to incident pipeline complexity.

Simple incidents skip Planner and Critic; complex incidents run all 5 agents.
Each agent argument accepts a single string (repeated on retries by MockLLMClient)
or a list of strings (consumed in order, then the last is repeated).
"""

from __future__ import annotations

from genai.clients.mock_client import MockLLMClient
from tests.unit.agents.incident.conftest import (
    CLASSIFIER_JSON,
    CRITIC_JSON,
    FIX_JSON,
    PLANNER_JSON,
    ROOT_CAUSE_JSON,
)

_R = str | list[str]


def _expand(r: _R) -> list[str]:
    return [r] if isinstance(r, str) else list(r)


class MockLLMClientBuilder:
    """Factory for MockLLMClient with correct response ordering per pipeline mode.

    Simple incidents: Planner skipped, Critic skipped → Classifier → RootCause → Fix
    Complex incidents: Planner → Classifier → RootCause → Fix → Critic
    """

    @staticmethod
    def simple(
        *,
        classifier: _R = CLASSIFIER_JSON,
        root_cause: _R = ROOT_CAUSE_JSON,
        fix: _R = FIX_JSON,
    ) -> MockLLMClient:
        """Responses for a simple incident pipeline (3 agents).

        Pass a list for any agent to simulate retries or deliberate failure, e.g.
        ``fix=["bad json", "bad json"]`` to exhaust FixAgent retries.
        """
        return MockLLMClient(_expand(classifier) + _expand(root_cause) + _expand(fix))

    @staticmethod
    def complex(
        *,
        planner: _R = PLANNER_JSON,
        classifier: _R = CLASSIFIER_JSON,
        root_cause: _R = ROOT_CAUSE_JSON,
        fix: _R = FIX_JSON,
        critic: _R = CRITIC_JSON,
    ) -> MockLLMClient:
        """Responses for a complex incident pipeline (all 5 agents).

        Pass a list for any agent to simulate retries or deliberate failure, e.g.
        ``planner=["bad json", "bad json"]`` to exhaust PlannerAgent retries.

        Note: when used for simple incidents (planner/critic skipped by orchestrator),
        the planner response is consumed by Classifier's first failed attempt before
        Classifier succeeds on retry. Use ``simple()`` when the incident complexity
        is known in advance.
        """
        return MockLLMClient(
            _expand(planner)
            + _expand(classifier)
            + _expand(root_cause)
            + _expand(fix)
            + _expand(critic)
        )
