from genai.prompts.base import BasePrompt


class CriticPrompt(BasePrompt):
    version = "1.0"

    @property
    def system(self) -> str:
        return (
            "You are a principal SRE reviewing an incident analysis for quality and accuracy. "
            "Assign a severity level and a confidence score based on the quality of the analysis. "
            "Score 0-25 on each criterion: root cause specificity, fix actionability, "
            "validation completeness, rollback feasibility. confidence_score = total / 100. "
            "Respond with ONLY a valid JSON object — no explanation, no markdown."
        )

    def user(self, **kwargs: str) -> str:
        return self._fill(_TEMPLATE, **kwargs)


_TEMPLATE = """\
Incident Analysis Review
========================
Service    : $service_name
Error      : $error_message

Root Cause          : $root_cause
Contributing Factors: $contributing_factors
Quick Fix           : $quick_fix
Long-term Fix       : $long_term_fix
Validation Steps    : $validation_steps
Rollback Plan       : $rollback_plan

Score the analysis (0-25 each) and assign severity:
- CRITICAL: service down, data loss risk, or cascading failure
- HIGH: major feature broken, significant user impact
- MEDIUM: partial degradation, workaround exists
- LOW: minor issue, no immediate user impact

Produce a JSON object with exactly these fields:
{
  "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
  "confidence_score": <0.0 to 1.0>,
  "review_notes": "<brief critique and scoring rationale>"
}
"""
