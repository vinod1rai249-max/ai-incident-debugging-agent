"""
AI agent that takes a CorrelationResult and produces an AIAnalysisResult.
Uses OpenRouter via the OpenAI-compatible client.
"""

import json
import os
import time

from models.correlation import AIAnalysisResult, CorrelationResult
from openai import AsyncOpenAI

from core.logging_config import get_logger
from core.metrics import ai_analysis_duration, analysis_requests_total

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a senior SRE (Site Reliability Engineer) AI agent.
Your task is to analyze a correlated set of ServiceNow incidents and Dynatrace problems,
then produce a concise root cause analysis and actionable resolution steps.

Always respond with a valid JSON object matching this exact schema:
{
  "incident_number": "<SN incident number>",
  "root_cause_summary": "<2-3 sentence root cause>",
  "contributing_factors": ["<factor 1>", "<factor 2>"],
  "suggested_resolution": "<concrete resolution steps>",
  "confidence": "HIGH | MEDIUM | LOW",
  "related_services": ["<service name>"],
  "recommended_actions": ["<action 1>", "<action 2>"]
}

Base your analysis ONLY on the provided data. Do not invent facts."""


def _build_analysis_prompt(correlation: CorrelationResult) -> str:
    inc = correlation.incident
    problems_text = ""
    for p in correlation.matched_problems:
        problems_text += (
            f"\n- Problem ID: {p.display_id}"
            f"\n  Title: {p.title}"
            f"\n  Severity: {p.severity_level}"
            f"\n  Impact: {p.impact_level}"
            f"\n  Status: {p.status}"
            f"\n  Services affected: {', '.join(p.service_names) or 'unknown'}"
            f"\n  Start time: {p.start_time.isoformat()}"
        )

    metrics_text = ""
    for m in correlation.service_metrics:
        metrics_text += (
            f"\n- Service: {m.service_name}  Error rate: {m.error_rate:.2f}%"
            if m.error_rate is not None
            else "" + (f"  Response time: {m.response_time_ms:.1f}ms" if m.response_time_ms else "")
        )

    return f"""Analyze this incident and correlated Dynatrace data:

=== ServiceNow Incident ===
Number: {inc.number}
Summary: {inc.short_description}
Description: {inc.description or "N/A"}
Priority: {inc.priority}
State: {inc.state_label}
Service/CI: {inc.service_name or "N/A"}
Opened: {inc.opened_at.isoformat() if inc.opened_at else "N/A"}

=== Correlated Dynatrace Problems ({len(correlation.matched_problems)}) ==={problems_text or " None found"}

=== Service Metrics ==={metrics_text or " No metrics available"}

=== Correlation Reasons ===
{chr(10).join(f"- {r}" for r in correlation.correlation_reasons) or "- No correlation reasons"}

Provide your root cause analysis as the JSON schema specified."""


class CorrelationAgent:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )

    async def analyze(self, correlation: CorrelationResult) -> AIAnalysisResult | None:
        incident_number = correlation.incident.number
        start = time.time()

        try:
            prompt = _build_analysis_prompt(correlation)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            response = await self._client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL"),
                messages=messages,
                max_tokens=1024,
                temperature=0,
            )
            raw_text = response.choices[0].message.content

            # Extract JSON block if wrapped in markdown
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()

            data = json.loads(raw_text)
            result = AIAnalysisResult(**data)

            elapsed = time.time() - start
            ai_analysis_duration.observe(elapsed)
            analysis_requests_total.labels(status="success").inc()
            logger.info("analysis_complete", incident=incident_number, duration_s=round(elapsed, 2))
            return result

        except Exception as exc:
            analysis_requests_total.labels(status="error").inc()
            logger.error("analysis_failed", incident=incident_number, error=str(exc))
            return None
