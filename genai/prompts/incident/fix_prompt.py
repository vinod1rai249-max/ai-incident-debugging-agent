from genai.prompts.base import BasePrompt


class FixPrompt(BasePrompt):
    version = "1.0"

    @property
    def system(self) -> str:
        return (
            "You are a senior SRE producing an actionable remediation plan. "
            "Separate the immediate on-call action from the long-term preventive fix. "
            "quick_fix must be executable in under 30 minutes. "
            "long_term_fix addresses root prevention (code, config, or process change). "
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

Root Cause         : $root_cause
Contributing Factors: $contributing_factors
Affected Components: $affected_components

Produce a JSON object with exactly these fields:
{
  "quick_fix": "<immediate on-call action, executable within 30 minutes>",
  "long_term_fix": "<preventive code, config, or process change to avoid recurrence>",
  "validation_steps": [
    "<step 1 — specific verifiable action>",
    "<step 2>",
    "..."
  ],
  "rollback_plan": "<safe rollback procedure with pre-conditions>"
}
"""
