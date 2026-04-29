from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from core.exceptions import AgentMaxStepsError
from core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_STEPS = 10


class AgentState(BaseModel):
    run_id: str
    step: int = 0
    plan: list[str] = []
    observations: list[str] = []
    final_answer: str = ""


class BaseAgent(ABC):
    def __init__(self, max_steps: int = DEFAULT_MAX_STEPS) -> None:
        self.max_steps = max_steps

    async def run(self, task: str, **kwargs: Any) -> AgentState:
        state = AgentState(run_id=self._new_run_id())
        logger.info("agent_run_start", run_id=state.run_id, task=task)

        state.plan = await self.plan(task, state)

        while state.step < self.max_steps:
            if state.final_answer:
                break
            state = await self.act(state, **kwargs)
            state.step += 1
        else:
            raise AgentMaxStepsError(self.max_steps)

        logger.info("agent_run_complete", run_id=state.run_id, steps=state.step)
        return state

    @abstractmethod
    async def plan(self, task: str, state: AgentState) -> list[str]: ...

    @abstractmethod
    async def act(self, state: AgentState, **kwargs: Any) -> AgentState: ...

    def _new_run_id(self) -> str:
        import uuid

        return str(uuid.uuid4())
