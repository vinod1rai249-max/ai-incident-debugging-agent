from genai.prompts.rag_prompt import RAGPrompt


def test_rag_prompt_renders_variables() -> None:
    prompt = RAGPrompt()
    system, user = prompt.render(context="Paris is in France.", question="Where is Paris?")
    assert "Paris is in France." in user
    assert "Where is Paris?" in user
    # rendered variable values must not leak into the static system prompt
    assert "Paris is in France." not in system
    assert "Where is Paris?" not in system


def test_rag_prompt_system_is_stable() -> None:
    p1, p2 = RAGPrompt(), RAGPrompt()
    assert p1.system == p2.system


def test_rag_prompt_version() -> None:
    assert RAGPrompt.version == "1.0"
