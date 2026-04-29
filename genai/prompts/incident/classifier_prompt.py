from genai.prompts.base import BasePrompt


class ClassifierPrompt(BasePrompt):
    version = "1.0"

    @property
    def system(self) -> str:
        return (
            "You are an expert SRE incident classifier. "
            "Classify the error category and extract the key diagnostic signals. "
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

Analysis Plan (from Planner):
$analysis_plan

Produce a JSON object with exactly these fields:
{
  "error_category": "<e.g. NullReference | DatabaseError | OOM | RateLimit | Config | Concurrency>",
  "key_signals": ["<specific signal 1>", "..."],
  "analysis_plan": "<one-paragraph description of how to analyse this incident>"
}
"""
