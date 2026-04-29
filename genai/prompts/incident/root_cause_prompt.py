from genai.prompts.base import BasePrompt


class RootCausePrompt(BasePrompt):
    version = "2.0"

    @property
    def system(self) -> str:
        return (
            "You are a senior SRE performing deep root cause analysis. "
            "Identify the exact root cause, contributing factors, and affected components. "
            "Be specific and concise — root_cause must be 1-2 sentences naming the exact"
            " component, mechanism, or code path that failed.\n"
            "When similar past incidents are provided:\n"
            "  - Compare the current error against each past incident by [index].\n"
            "  - Identify which past incident most closely matches the current failure pattern.\n"
            "  - Reference the matching past incident in root_cause only if it directly applies.\n"
            "  - Adapt relevant past fixes to the current context — never copy verbatim.\n"
            "  - If no past incident is relevant, perform fully independent analysis.\n"
            "Respond with ONLY a valid JSON object — no explanation, no markdown."
        )

    def user(self, **kwargs: str) -> str:
        return self._fill(_TEMPLATE, **kwargs)


_TEMPLATE = """\
Incident Details
================
Service    : $service_name
Environment: $environment
Error      : $error_message

Stack Trace:
$stack_trace

Logs:
$logs
$code_block

Error Category : $error_category
Key Signals    : $key_signals
$rag_context
Produce a JSON object with exactly these fields:
{
  "root_cause": "<1-2 sentences: exact cause and component; reference past [N] only if directly applicable>",
  "contributing_factors": ["<factor 1>", "..."],
  "affected_components": ["<component 1>", "..."]
}
"""
