from core.exceptions import AgentMaxStepsError, AppError, LLMError, ToolError


def test_app_error_defaults() -> None:
    err = AppError("something went wrong")
    assert err.code == "APP_ERROR"
    assert str(err) == "something went wrong"


def test_llm_error_code() -> None:
    assert LLMError("fail").code == "LLM_ERROR"


def test_tool_error_carries_name() -> None:
    err = ToolError("bad tool", tool_name="search")
    assert err.tool_name == "search"
    assert err.code == "TOOL_ERROR"


def test_agent_max_steps_error() -> None:
    err = AgentMaxStepsError(10)
    assert err.max_steps == 10
    assert "10" in str(err)
