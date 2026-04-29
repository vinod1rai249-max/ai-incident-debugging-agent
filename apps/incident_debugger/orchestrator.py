from __future__ import annotations

import hashlib
import re
import time
import uuid

import structlog

from agents.incident.classifier_agent import ClassifierAgent
from agents.incident.critic_agent import CriticAgent
from agents.incident.fix_agent import FixAgent
from agents.incident.planner_agent import PlannerAgent
from agents.incident.root_cause_agent import RootCauseAgent
from apps.incident_debugger.metrics import (
    degraded_response_total,
    incident_agent_cost_usd,
    incident_agent_duration_seconds,
    incident_analysis_duration_seconds,
    incident_analysis_failure_total,
    incident_analysis_success_total,
    incident_analysis_total,
    incident_confidence_score,
    incident_cost_usd_total,
    rag_source_hits_total,
)
from apps.incident_debugger.metrics import (
    retrieved_docs_count as incident_retrieved_docs_count,
)
from apps.incident_debugger.models import (
    AgentStepTrace,
    AnalysisMetadata,
    CriticResult,
    FixResult,
    IncidentInput,
    IncidentReport,
    PlannerResult,
    RetrievedDocSummary,
    RootCauseResult,
    SeverityLevel,
    TriageResult,
)
from core.circuit_breaker import CircuitBreaker
from core.config import settings
from core.cost import CostAccumulator, TokenUsage
from core.exceptions import IncidentCostLimitError
from genai.clients.base import BaseLLMClient
from genai.rag.retrieval.base import BaseRetriever

logger = structlog.get_logger(__name__)

_CACHE_TTL_S: float = 300.0  # 5-minute fingerprint cache TTL

# Environments in which dev-only force flags (force_degraded, force_blocking_failure)
# are honoured.  Any other environment value — including "production" and "staging" —
# causes the flags to be silently ignored even if they are set on the request.
_DEV_ENVIRONMENTS: frozenset[str] = frozenset({"dev", "local"})

# Patterns that indicate high complexity requiring full pipeline
_HIGH_COMPLEXITY_PATTERNS = re.compile(
    r"(deadlock|cascad|memory.?leak|oom|out.?of.?memory|circuit.?break|"
    r"infinite.?loop|retry.?storm|data.?corrup|critical|sev[- ]?1)",
    re.IGNORECASE,
)

_LOG_NOISE = re.compile(
    r"^(?:DEBUG|INFO|TRACE|VERBOSE)\b",
    re.IGNORECASE,
)

# Fast planner fallback used for simple incidents (no LLM call)
_FAST_PLANNER_RESULT = PlannerResult(
    steps=["Classify error category", "Identify root cause", "Suggest fix"],
    priority_signals=["error_message", "stack_trace"],
    estimated_complexity="simple",
)

# Safe defaults used when non-blocking agents fail
_FALLBACK_FIX = FixResult(
    quick_fix="Consult on-call runbook — automated fix analysis unavailable.",
    long_term_fix="Investigate root cause manually and implement a preventive code fix.",
    validation_steps=[
        "Check service health endpoint and recent error rate.",
        "Review recent deployments in the last 24 hours.",
    ],
    rollback_plan="Follow standard rollback procedure in the on-call runbook.",
)
_FALLBACK_CRITIC = CriticResult(
    severity=SeverityLevel.HIGH,
    confidence_score=0.3,
    review_notes="Critic analysis unavailable — defaulting to HIGH severity with low confidence.",
)


class IncidentOrchestrator:
    """Runs the 5-agent pipeline: Planner → Classifier → RootCause → Fix → Critic.

    Blocking agents (Classifier, RootCause): failure raises IncidentAnalysisError.
    Non-blocking agents (Planner, Fix, Critic): failure uses safe defaults, sets degraded=True.
    Cost ceiling: raises IncidentCostLimitError if exceeded mid-pipeline.
    RAG: optional retriever enriches RootCauseAgent context with similar past incidents.
    """

    MAX_COST_USD: float = 0.10

    def __init__(
        self,
        llm_client: BaseLLMClient,
        circuit_breaker: CircuitBreaker | None = None,
        max_retries: int = 3,
        base_wait_s: float = 1.0,
        retriever: BaseRetriever | None = None,
        fast_llm_client: BaseLLMClient | None = None,
    ) -> None:
        cb = circuit_breaker or CircuitBreaker(
            name="incident_llm",
            failure_threshold=0.5,
            min_calls=5,
            recovery_timeout=30.0,
        )
        # fast_llm_client is used for lightweight agents (Planner) when a
        # cheaper/faster model is configured.  Falls back to llm_client if absent.
        fast_client = fast_llm_client or llm_client
        fast_kwargs = dict(
            llm_client=fast_client,
            circuit_breaker=cb,
            max_retries=max_retries,
            base_wait_s=base_wait_s,
        )
        std_kwargs = dict(
            llm_client=llm_client,
            circuit_breaker=cb,
            max_retries=max_retries,
            base_wait_s=base_wait_s,
        )
        self._planner = PlannerAgent(**fast_kwargs)
        self._classifier = ClassifierAgent(**fast_kwargs)  # Haiku — lightweight triage
        self._root_cause = RootCauseAgent(**std_kwargs)
        self._fix = FixAgent(**std_kwargs)
        self._critic = CriticAgent(**fast_kwargs)  # Haiku — scoring only
        self._retriever = retriever
        # Per-instance fingerprint cache: fp → (report, expiry_monotonic)
        self._cache: dict[str, tuple[IncidentReport, float]] = {}

    async def run(self, incident: IncidentInput) -> IncidentReport:
        # ── Dev-only test hooks — bypass cache and full pipeline ──────────
        # Flags are honoured only when the request environment is "dev" or
        # "local" AND the server itself is not running in production mode.
        # This prevents accidental activation against real incidents.
        if (
            incident.environment in _DEV_ENVIRONMENTS
            and not settings.is_production
        ):
            if incident.force_blocking_failure:
                return self._force_blocking_failure_response(incident)
            if incident.force_degraded:
                return self._force_degraded_response(incident)

        # ── Fingerprint cache ─────────────────────────────────────────────
        fp = _fingerprint(incident)
        now = time.monotonic()
        cached = self._cache.get(fp)
        if cached and now < cached[1]:
            logger.info("orchestrator.cache_hit", fingerprint=fp[:12])
            return cached[0]

        incident_id = str(uuid.uuid4())
        pipeline_start = now
        accumulator = CostAccumulator()
        traces: list[AgentStepTrace] = []
        degraded = False
        retrieved_docs_count = 0
        retrieved_doc_summaries: list[RetrievedDocSummary] = []
        rag_sources: list[str] = []

        # Compact logs to ERROR/WARN/Exception lines, max 30 lines
        incident = _compact_incident_logs(incident)

        # Determine whether this is a complex incident (needs full pipeline)
        run_full_pipeline = _is_complex(incident)

        logger.info(
            "orchestrator.start",
            incident_id=incident_id,
            service=incident.service_name,
            environment=incident.environment,
            full_pipeline=run_full_pipeline,
        )

        # ── Step 1: Planner (NON-BLOCKING, skipped for simple incidents) ──
        planner_result: PlannerResult
        if run_full_pipeline:
            try:
                planner_result, trace = await self._planner.run(incident=incident)
                traces.append(trace)
                self._check_cost(accumulator, trace, incident_id)
                _record_agent_metrics(trace)
            except Exception as exc:
                logger.warning(
                    "orchestrator.planner_fallback", incident_id=incident_id, error=str(exc)
                )
                planner_result = _FAST_PLANNER_RESULT
                traces.append(_error_trace("PlannerAgent", exc))
                degraded = True
        else:
            logger.info(
                "orchestrator.planner_skipped", incident_id=incident_id, reason="simple incident"
            )
            planner_result = _FAST_PLANNER_RESULT

        # ── Step 2: Classifier (BLOCKING) ─────────────────────────────────
        classifier_result: TriageResult
        try:
            classifier_result, trace = await self._classifier.run(
                incident=incident, planner=planner_result
            )
            traces.append(trace)
            self._check_cost(accumulator, trace, incident_id)
            _record_agent_metrics(trace)
        except Exception as exc:
            logger.error("orchestrator.classifier_failed", incident_id=incident_id, error=str(exc))
            return self._degraded_report(
                incident_id,
                traces,
                accumulator,
                pipeline_start,
                exc,
                environment=incident.environment,
            )

        # ── RAG retrieval (optional) ───────────────────────────────────────
        rag_context = ""
        if self._retriever is not None:
            query = f"{incident.error_message} {incident.stack_trace}"
            try:
                docs = await self._retriever.retrieve(query, top_k=2)
                retrieved_docs_count = len(docs)
                if docs:
                    # Compact format: only the fields agents actually need
                    rag_context = "\n".join(
                        f"[{i + 1}] id={d.source} sev={d.metadata.get('severity', '')} "
                        f"cause={d.metadata.get('root_cause', d.content[:120])} "
                        f"fix={d.metadata.get('fix_summary', '')}"
                        for i, d in enumerate(docs)
                    )
                    retrieved_doc_summaries = [
                        RetrievedDocSummary(
                            source=d.source,
                            description=d.metadata.get("description", ""),
                            severity=d.metadata.get("severity", ""),
                            score=round(d.score, 4),
                        )
                        for d in docs
                    ]
                    # Unique source systems, order-preserving
                    rag_sources = list(
                        dict.fromkeys(d.metadata.get("source_system", d.source) for d in docs)
                    )
                    logger.info(
                        "orchestrator.rag_retrieved",
                        incident_id=incident_id,
                        docs_count=retrieved_docs_count,
                        sources=rag_sources,
                    )
                    for _d in docs:
                        rag_source_hits_total.labels(
                            source=_d.metadata.get("source_system", _d.source)
                        ).inc()
            except Exception as exc:
                logger.warning("orchestrator.rag_failed", incident_id=incident_id, error=str(exc))
        incident_retrieved_docs_count.observe(retrieved_docs_count)

        # ── Step 3: RootCause (BLOCKING) ──────────────────────────────────
        root_cause_result: RootCauseResult
        try:
            root_cause_result, trace = await self._root_cause.run(
                incident=incident,
                classifier=classifier_result,
                rag_context=rag_context,
            )
            traces.append(trace)
            self._check_cost(accumulator, trace, incident_id)
            _record_agent_metrics(trace)
        except Exception as exc:
            logger.error("orchestrator.root_cause_failed", incident_id=incident_id, error=str(exc))
            return self._degraded_report(
                incident_id,
                traces,
                accumulator,
                pipeline_start,
                exc,
                environment=incident.environment,
            )

        # ── Step 4: Fix (NON-BLOCKING) ────────────────────────────────────
        fix_result: FixResult
        fix_failure_reason: str | None = None
        try:
            fix_result, trace = await self._fix.run(incident=incident, root_cause=root_cause_result)
            traces.append(trace)
            self._check_cost(accumulator, trace, incident_id)
            _record_agent_metrics(trace)
        except Exception as exc:
            logger.warning("orchestrator.fix_fallback", incident_id=incident_id, error=str(exc))
            fix_result = _FALLBACK_FIX
            traces.append(_error_trace("FixAgent", exc))
            degraded = True
            fix_failure_reason = _classify_fix_failure(exc)

        # ── Step 5: Critic (NON-BLOCKING, skipped for simple incidents) ───
        critic_result: CriticResult
        if run_full_pipeline:
            try:
                critic_result, trace = await self._critic.run(
                    incident=incident, root_cause=root_cause_result, fix=fix_result
                )
                traces.append(trace)
                self._check_cost(accumulator, trace, incident_id)
                _record_agent_metrics(trace)
            except Exception as exc:
                logger.warning(
                    "orchestrator.critic_fallback", incident_id=incident_id, error=str(exc)
                )
                critic_result = _FALLBACK_CRITIC
                traces.append(_error_trace("CriticAgent", exc))
                degraded = True
        else:
            logger.info(
                "orchestrator.critic_skipped", incident_id=incident_id, reason="simple incident"
            )
            critic_result = _FALLBACK_CRITIC

        total_latency_s = time.monotonic() - pipeline_start
        total_latency_ms = total_latency_s * 1000
        total_cost = accumulator.total_cost_usd

        # ── Prometheus pipeline metrics ────────────────────────────────────
        incident_analysis_total.labels(
            severity=critic_result.severity.value,
            environment=incident.environment,
        ).inc()
        incident_analysis_duration_seconds.observe(total_latency_s)
        incident_confidence_score.labels(severity=critic_result.severity.value).observe(
            critic_result.confidence_score
        )
        incident_cost_usd_total.observe(total_cost)
        if not degraded:
            incident_analysis_success_total.labels(
                severity=critic_result.severity.value,
                environment=incident.environment,
            ).inc()
        else:
            degraded_response_total.labels(environment=incident.environment).inc()

        report = IncidentReport(
            incident_id=incident_id,
            root_cause=root_cause_result.root_cause,
            severity=critic_result.severity,
            confidence_score=critic_result.confidence_score,
            quick_fix=fix_result.quick_fix,
            long_term_fix=fix_result.long_term_fix,
            validation_steps=fix_result.validation_steps,
            rollback_plan=fix_result.rollback_plan,
            metadata=AnalysisMetadata(
                total_cost_usd=round(total_cost, 6),
                total_latency_ms=round(total_latency_ms, 2),
                models_used=_unique_models(traces),
                agent_trace=traces,
                degraded=degraded,
                failure_reason=fix_failure_reason,
                retrieved_docs_count=retrieved_docs_count,
                retrieved_docs=retrieved_doc_summaries,
                rag_sources=rag_sources,
            ),
        )

        logger.info(
            "orchestrator.complete",
            incident_id=incident_id,
            severity=report.severity,
            confidence=report.confidence_score,
            cost_usd=report.metadata.total_cost_usd,
            latency_ms=round(total_latency_ms, 1),
            degraded=degraded,
            retrieved_docs=retrieved_docs_count,
        )

        # Store in per-instance fingerprint cache
        self._cache[fp] = (report, time.monotonic() + _CACHE_TTL_S)
        return report

    # ------------------------------------------------------------------
    # Dev-only test hooks
    # ------------------------------------------------------------------

    def _force_blocking_failure_response(self, incident: IncidentInput) -> IncidentReport:
        incident_id = str(uuid.uuid4())
        logger.warning(
            "orchestrator.dev_flag.force_blocking_failure",
            incident_id=incident_id,
            environment=incident.environment,
        )
        return self._degraded_report(
            incident_id=incident_id,
            traces=[],
            accumulator=CostAccumulator(),
            pipeline_start=time.monotonic(),
            exc=RuntimeError("force_blocking_failure=True"),
            environment=incident.environment,
        )

    def _force_degraded_response(self, incident: IncidentInput) -> IncidentReport:
        incident_id = str(uuid.uuid4())
        logger.warning(
            "orchestrator.dev_flag.force_degraded",
            incident_id=incident_id,
            environment=incident.environment,
        )
        degraded_response_total.labels(environment=incident.environment).inc()
        return IncidentReport(
            incident_id=incident_id,
            root_cause="Forced degraded response for testing (force_degraded=True).",
            severity=_FALLBACK_CRITIC.severity,
            confidence_score=_FALLBACK_CRITIC.confidence_score,
            quick_fix=_FALLBACK_FIX.quick_fix,
            long_term_fix=_FALLBACK_FIX.long_term_fix,
            validation_steps=_FALLBACK_FIX.validation_steps,
            rollback_plan=_FALLBACK_FIX.rollback_plan,
            metadata=AnalysisMetadata(
                total_cost_usd=0.0,
                total_latency_ms=0.0,
                models_used=[],
                agent_trace=[],
                degraded=True,
            ),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_cost(
        self, accumulator: CostAccumulator, trace: AgentStepTrace, incident_id: str
    ) -> None:
        usage = TokenUsage(
            model=trace.model_id,
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
        )
        accumulator.add(usage)
        if accumulator.total_cost_usd > self.MAX_COST_USD:
            raise IncidentCostLimitError(
                f"Budget exceeded: ${accumulator.total_cost_usd:.4f} > ${self.MAX_COST_USD}"
            )

    def _degraded_report(
        self,
        incident_id: str,
        traces: list[AgentStepTrace],
        accumulator: CostAccumulator,
        pipeline_start: float,
        exc: Exception,
        environment: str = "unknown",
    ) -> IncidentReport:
        incident_analysis_failure_total.labels(environment=environment).inc()
        total_latency_ms = (time.monotonic() - pipeline_start) * 1000
        return IncidentReport(
            incident_id=incident_id,
            root_cause=f"Analysis incomplete — pipeline stopped: {exc}",
            severity=SeverityLevel.HIGH,
            confidence_score=0.0,
            quick_fix=_FALLBACK_FIX.quick_fix,
            long_term_fix=_FALLBACK_FIX.long_term_fix,
            validation_steps=_FALLBACK_FIX.validation_steps,
            rollback_plan=_FALLBACK_FIX.rollback_plan,
            metadata=AnalysisMetadata(
                total_cost_usd=round(accumulator.total_cost_usd, 6),
                total_latency_ms=round(total_latency_ms, 2),
                models_used=_unique_models(traces),
                agent_trace=traces,
                degraded=True,
            ),
        )


def _record_agent_metrics(trace: AgentStepTrace) -> None:
    incident_agent_duration_seconds.labels(agent_name=trace.agent_name).observe(
        trace.latency_ms / 1000.0
    )
    incident_agent_cost_usd.labels(agent_name=trace.agent_name, model=trace.model_id).observe(
        trace.cost_usd
    )


def _error_trace(agent_name: str, exc: Exception) -> AgentStepTrace:
    return AgentStepTrace(
        agent_name=agent_name,
        model_id="unknown",
        status="error",
        latency_ms=0.0,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        error=str(exc),
    )


def _unique_models(traces: list[AgentStepTrace]) -> list[str]:
    seen: dict[str, None] = {}
    for t in traces:
        if t.model_id != "unknown":
            seen[t.model_id] = None
    return list(seen)


def _fingerprint(incident: IncidentInput) -> str:
    key = f"{incident.error_message}||{incident.stack_trace[:500]}"
    return hashlib.sha256(key.encode()).hexdigest()


def _is_complex(incident: IncidentInput) -> bool:
    combined = f"{incident.error_message} {incident.stack_trace} {incident.logs}"
    return bool(_HIGH_COMPLEXITY_PATTERNS.search(combined))


def _classify_fix_failure(exc: Exception) -> str:
    """Return a human-readable reason string for a FixAgent failure."""
    exc_str = str(exc)
    if any(k in exc_str.lower() for k in ("json", "decode", "parse")):
        return "FixAgent failed due to invalid JSON after retries"
    return f"FixAgent failed — {exc_str[:120]}"


def _compact_incident_logs(incident: IncidentInput) -> IncidentInput:
    if not incident.logs:
        return incident
    lines = incident.logs.splitlines()
    kept = [ln for ln in lines if not _LOG_NOISE.match(ln.lstrip()) and ln.strip()][:30]
    compact_logs = "\n".join(kept)
    return incident.model_copy(update={"logs": compact_logs})
