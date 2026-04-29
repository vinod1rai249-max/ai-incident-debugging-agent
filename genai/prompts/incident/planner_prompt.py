from genai.prompts.base import BasePrompt


class PlannerPrompt(BasePrompt):
    version = "1.0"

    @property
    def system(self) -> str:
        return (
            "You are an expert SRE incident analyst. "
            "Given a production incident, produce a structured analysis plan. "
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

Produce a JSON object with exactly these fields:
{
  "steps": ["<ordered analysis step 1>", "..."],
  "priority_signals": ["<key signal to investigate 1>", "..."],
  "estimated_complexity": "<simple|moderate|complex>"
}
"""
