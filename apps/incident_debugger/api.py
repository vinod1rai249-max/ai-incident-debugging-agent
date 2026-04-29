from __future__ import annotations

import asyncio
import json
import pathlib

import structlog
from fastapi import APIRouter, Depends

from apps.incident_debugger.models import IncidentInput, IncidentReport
from apps.incident_debugger.orchestrator import IncidentOrchestrator
from core.circuit_breaker import CircuitBreaker
from core.config import settings
from genai.clients.base import BaseLLMClient
from genai.clients.mock_client import MockLLMClient
from genai.connectors.dynatrace_connector import DynatraceConnector
from genai.connectors.servicenow_connector import ServiceNowConnector
from genai.rag.retrieval.tfidf_retriever import TFIDFRetriever

router = APIRouter(prefix="/incidents", tags=["incidents"])
logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Canned mock responses — one per agent in pipeline order.
# Used when ANTHROPIC_API_KEY is not a valid Anthropic key.
# ---------------------------------------------------------------------------
_MOCK_PLANNER = json.dumps(
    {
        "steps": ["Identify error type", "Analyse stack trace", "Check recent deployments"],
        "priority_signals": ["NullPointerException", "stack_trace", "service logs"],
        "estimated_complexity": "moderate",
    }
)
_MOCK_CLASSIFIER = json.dumps(
    {
        "error_category": "NullReference",
        "key_signals": ["NoneType", "attribute access", "missing null guard"],
        "analysis_plan": "Investigate the call site where a None value is dereferenced.",
    }
)
_MOCK_ROOT_CAUSE = json.dumps(
    {
        "root_cause": (
            "The transaction object returned by db.get_transaction() is None"
            " when no row is found, and the caller dereferences it without a null guard."
        ),
        "contributing_factors": [
            "Missing null check before attribute access",
            "No default return value from DB layer",
        ],
        "affected_components": ["payment-service", "transaction repository"],
    }
)
_MOCK_FIX = json.dumps(
    {
        "quick_fix": (
            "Add a null guard in process_payment(): if transaction is None,"
            " raise a PaymentNotFoundError with the order_id before accessing charge_id."
        ),
        "long_term_fix": (
            "Update db.get_transaction() to raise TransactionNotFoundError instead of"
            " returning None; enforce the contract at the repository layer."
        ),
        "validation_steps": [
            "Deploy fix and run integration test suite against staging.",
            "Verify no new AttributeErrors appear in payment-service logs for 10 minutes.",
            "Confirm order ORD-9921 can be processed end-to-end in staging.",
        ],
        "rollback_plan": (
            "Revert the fix commit and redeploy the previous image tag"
            " if error rate rises above 1% within 5 minutes of deployment."
        ),
    }
)
_MOCK_CRITIC = json.dumps(
    {
        "severity": "HIGH",
        "confidence_score": 0.85,
        "review_notes": (
            "Root cause is specific and actionable. Fix is concrete."
            " Validation steps are verifiable. Rollback has clear pre-conditions."
        ),
    }
)

# RAG corpus fixtures — ServiceNow and Dynatrace MuleSoft healthcare sources.
_PROJECT_ROOT = pathlib.Path(__file__).parent.parent.parent
_SN_FIXTURE = _PROJECT_ROOT / "data" / "servicenow_mulesoft_healthcare_incidents.json"
_DT_FIXTURE = _PROJECT_ROOT / "data" / "dynatrace_mulesoft_logs.json"

# ---------------------------------------------------------------------------
# Module-level cached retriever — built once on first request.
# ---------------------------------------------------------------------------
_SHARED_RETRIEVER: TFIDFRetriever | None = None
_RETRIEVER_LOCK = asyncio.Lock()


async def _get_shared_retriever() -> TFIDFRetriever:
    """Return the module-level TF-IDF retriever, built once on first call.

    Seeds from two MuleSoft healthcare sources so retrieved docs always carry
    a ``source_system`` label of ``"servicenow"`` or ``"dynatrace"``.
    """
    global _SHARED_RETRIEVER
    if _SHARED_RETRIEVER is not None:
        return _SHARED_RETRIEVER
    async with _RETRIEVER_LOCK:
        if _SHARED_RETRIEVER is None:
            retriever = TFIDFRetriever()
            docs = []

            if _SN_FIXTURE.exists():
                try:
                    sn_docs = ServiceNowConnector(fixture_path=_SN_FIXTURE).to_documents()
                    docs.extend(sn_docs)
                    logger.info("api.retriever_sn_loaded", count=len(sn_docs))
                except Exception as exc:
                    logger.warning("api.retriever_sn_failed", error=str(exc))

            if _DT_FIXTURE.exists():
                try:
                    dt_docs = DynatraceConnector(fixture_path=_DT_FIXTURE).to_documents()
                    docs.extend(dt_docs)
                    logger.info("api.retriever_dt_loaded", count=len(dt_docs))
                except Exception as exc:
                    logger.warning("api.retriever_dt_failed", error=str(exc))

            if docs:
                await retriever.add_documents(docs)
                logger.info(
                    "api.retriever_initialized",
                    total_docs=len(docs),
                    sources=["servicenow", "dynatrace"],
                )

            _SHARED_RETRIEVER = retriever
    return _SHARED_RETRIEVER


# ---------------------------------------------------------------------------
# LLM client factory
# ---------------------------------------------------------------------------


def _is_real_key(key: str) -> bool:
    return bool(key) and key.startswith("sk-ant-")


def _make_mock_client() -> BaseLLMClient:
    return MockLLMClient(
        responses=[
            _MOCK_PLANNER,
            _MOCK_CLASSIFIER,
            _MOCK_ROOT_CAUSE,
            _MOCK_FIX,
            _MOCK_CRITIC,
        ]
    )


def _make_llm_clients() -> tuple[BaseLLMClient, BaseLLMClient | None]:
    """Return (standard_client, fast_client_or_None).

    standard_client is used for ClassifierAgent, RootCauseAgent, FixAgent, CriticAgent.
    fast_client    is used for PlannerAgent (Haiku when real key configured).
    """
    key = settings.anthropic_api_key
    if _is_real_key(key):
        from genai.clients.anthropic_client import AnthropicClient

        std = AnthropicClient(model=settings.model_name)
        fast = AnthropicClient(model="claude-haiku-4-5-20251001")
        return std, fast
    return _make_mock_client(), None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_orchestrator() -> IncidentOrchestrator:
    """Async dependency — retriever is initialized once and reused across requests."""
    retriever = await _get_shared_retriever()
    std_client, fast_client = _make_llm_clients()
    key = settings.anthropic_api_key
    return IncidentOrchestrator(
        llm_client=std_client,
        fast_llm_client=fast_client,
        circuit_breaker=CircuitBreaker(
            name="incident_llm",
            failure_threshold=0.5,
            min_calls=5,
            recovery_timeout=30.0,
        ),
        base_wait_s=0.0 if not _is_real_key(key) else 1.0,
        retriever=retriever,
    )


@router.post("/analyze", response_model=IncidentReport)
async def analyze_incident(
    payload: IncidentInput,
    orchestrator: IncidentOrchestrator = Depends(get_orchestrator),  # noqa: B008
) -> IncidentReport:
    logger.info(
        "incident.analyze.request",
        service=payload.service_name,
        environment=payload.environment,
    )
    return await orchestrator.run(payload)
