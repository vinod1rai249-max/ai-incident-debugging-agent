class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, code: str = "APP_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class LLMError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="LLM_ERROR")


class RetrieverError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="RETRIEVER_ERROR")


class ToolError(AppError):
    def __init__(self, message: str, tool_name: str = "") -> None:
        super().__init__(message, code="TOOL_ERROR")
        self.tool_name = tool_name


class ValidationError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="VALIDATION_ERROR")


class PlanningError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="PLANNING_ERROR")


class AgentMaxStepsError(AppError):
    def __init__(self, max_steps: int) -> None:
        super().__init__(f"Agent exceeded max steps: {max_steps}", code="AGENT_MAX_STEPS")
        self.max_steps = max_steps


class IncidentAnalysisError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="INCIDENT_ANALYSIS_ERROR")


class IncidentCostLimitError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="INCIDENT_COST_LIMIT")
