"""
Milestone 4A - Single controlled real LLM test.

Runs case_001 (AttributeError/NoneType) through the full IncidentOrchestrator
using AnthropicClient directly.  Prints a structured audit of:
  - request payload
  - response quality
  - per-agent trace
  - total cost
  - total latency
  - degraded status + root cause of any failure

Max cost ceiling: $0.10 (enforced by orchestrator).
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import time

from apps.incident_debugger.models import IncidentInput, IncidentReport
from apps.incident_debugger.orchestrator import IncidentOrchestrator
from core.config import settings
from genai.clients.anthropic_client import AnthropicClient
from genai.rag.retrieval.base import Document
from genai.rag.retrieval.tfidf_retriever import TFIDFRetriever

_FIXTURES_PATH = pathlib.Path(__file__).parent.parent / "tests" / "fixtures" / "incident_cases.json"

SEP = "=" * 72
DIV = "-" * 72


def _load_case(case_id: str = "case_001") -> dict:
    cases = json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))
    return next(c for c in cases if c["id"] == case_id)


def _is_real_key(key: str) -> bool:
    return bool(key) and key.startswith("sk-ant-")


def _make_clients() -> tuple[object, object | None, bool]:
    """Return (std_client, fast_client_or_None, key_is_valid)."""
    key = settings.anthropic_api_key
    if _is_real_key(key):
        print(f"[CLIENT] std={settings.model_name}  fast=claude-haiku-4-5-20251001")
        std = AnthropicClient(model=settings.model_name)
        fast = AnthropicClient(model="claude-haiku-4-5-20251001")
        return std, fast, True
    else:
        print("[CLIENT] No valid ANTHROPIC_API_KEY found.")
        print("         Forcing AnthropicClient to demonstrate real-API failure path.")
        print("         This will produce a DEGRADED response per Milestone 4A constraints.")
        return AnthropicClient(model=settings.model_name), None, False


async def _build_retriever() -> TFIDFRetriever:
    retriever = TFIDFRetriever()
    if _FIXTURES_PATH.exists():
        cases = json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))
        docs = [
            Document(
                content=(
                    f"{c['input']['error_message']} "
                    f"{c['input']['stack_trace']} "
                    f"{c['input']['logs']}"
                ),
                source=c["id"],
                metadata={"severity": c["expected"]["severity"]},
            )
            for c in cases
        ]
        await retriever.add_documents(docs)
    print(f"[RAG]    Retriever seeded with {len(docs)} incident cases from fixture")
    return retriever


async def main() -> None:
    case = _load_case("case_001")
    inp = case["input"]
    expected = case["expected"]

    incident = IncidentInput(
        error_message=inp["error_message"],
        stack_trace=inp["stack_trace"],
        logs=inp["logs"],
        code_snippet=inp.get("code_snippet"),
        service_name=inp.get("service_name"),
        environment=inp.get("environment", "production"),
    )

    print(SEP)
    print("MILESTONE 4A -- Real LLM Single Incident Test")
    print(SEP)
    print(f"\n[CASE]   {case['id']} -- {case['description']}")
    print(
        f"[EXPECT] severity={expected['severity']}, "
        f"min_confidence={expected['min_confidence']}, "
        f"keywords={expected['root_cause_keywords']}"
    )

    print(f"\n{DIV}")
    print("REQUEST PAYLOAD")
    print(DIV)
    print(f"  error_message : {incident.error_message}")
    print(f"  stack_trace   : {incident.stack_trace[:80]}...")
    print(f"  logs          : {incident.logs[:80]}...")
    print(f"  service_name  : {incident.service_name}")
    print(f"  environment   : {incident.environment}")

    std_client, fast_client, key_valid = _make_clients()
    retriever = await _build_retriever()

    orchestrator = IncidentOrchestrator(
        llm_client=std_client,
        fast_llm_client=fast_client,
        max_retries=2,
        base_wait_s=1.0,
        retriever=retriever,
    )
    orchestrator.MAX_COST_USD = 0.10

    wall_start = time.monotonic()
    report: IncidentReport = await orchestrator.run(incident)
    wall_elapsed_s = time.monotonic() - wall_start

    # RESPONSE QUALITY
    print(f"\n{DIV}")
    print("RESPONSE QUALITY")
    print(DIV)
    print(f"  incident_id     : {report.incident_id}")
    print(f"  severity        : {report.severity.value}")
    print(f"  confidence_score: {report.confidence_score:.2f}")
    print(f"  degraded        : {report.metadata.degraded}")
    print(f"\n  root_cause:\n    {report.root_cause}")
    print(f"\n  quick_fix:\n    {report.quick_fix}")
    print(f"\n  long_term_fix:\n    {report.long_term_fix}")
    print("\n  validation_steps:")
    for i, step in enumerate(report.validation_steps, 1):
        print(f"    {i}. {step}")
    print(f"\n  rollback_plan:\n    {report.rollback_plan}")

    # AGENT TRACE
    print(f"\n{DIV}")
    print("AGENT TRACE  (per-agent)")
    print(DIV)
    print(
        f"  {'Agent':<22} {'Status':<10} {'Model':<22} "
        f"{'Latency':>10} {'InTok':>7} {'OutTok':>7} {'CostUSD':>10}"
    )
    print(f"  {'-' * 22} {'-' * 10} {'-' * 22} {'-' * 10} {'-' * 7} {'-' * 7} {'-' * 10}")
    for t in report.metadata.agent_trace:
        print(
            f"  {t.agent_name:<22} {t.status:<10} {t.model_id:<22} "
            f"{t.latency_ms:>9.0f}ms {t.input_tokens:>7} {t.output_tokens:>7} "
            f"${t.cost_usd:>9.6f}"
        )
        if t.error:
            short_err = t.error[:110].replace("\n", " ")
            print(f"    error: {short_err}")

    # RETRIEVED CONTEXT (RAG)
    print(f"\n{DIV}")
    print("RAG -- RETRIEVED CONTEXT")
    print(DIV)
    print(f"  retrieved_docs_count : {report.metadata.retrieved_docs_count}")
    if report.metadata.retrieved_docs_count > 0:
        query = f"{incident.error_message} {incident.stack_trace[:60]}"
        docs = await retriever.retrieve(query, top_k=3)
        for i, d in enumerate(docs, 1):
            print(
                f"  [{i}] source={d.source}  score={d.score:.4f}  "
                f"severity={d.metadata.get('severity', '')}  "
                f"excerpt={d.content[:80]}..."
            )
    else:
        print("  (no documents retrieved)")

    # COST & LATENCY
    print(f"\n{DIV}")
    print("COST & LATENCY")
    print(DIV)
    print(
        f"  total_cost_usd   : ${report.metadata.total_cost_usd:.6f}"
        f"  (ceiling: ${orchestrator.MAX_COST_USD:.2f})"
    )
    print(
        f"  total_latency_ms : {report.metadata.total_latency_ms:,.0f} ms"
        f"  (pipeline, excl. tenacity retries)"
    )
    print(f"  wall_clock_s     : {wall_elapsed_s:.2f}s")
    print(f"  models_used      : {report.metadata.models_used}")
    print(f"  retrieved_docs   : {report.metadata.retrieved_docs_count}")

    # SEMANTIC VALIDATION
    print(f"\n{DIV}")
    print("SEMANTIC VALIDATION")
    print(DIV)
    severity_pass = report.severity.value == expected["severity"]
    confidence_pass = report.confidence_score >= expected["min_confidence"]
    keyword_pass = any(
        kw.lower() in report.root_cause.lower() for kw in expected["root_cause_keywords"]
    )
    checks = [
        ("severity match", severity_pass, f"{report.severity.value} == {expected['severity']}"),
        (
            "confidence >= min",
            confidence_pass,
            f"{report.confidence_score:.2f} >= {expected['min_confidence']}",
        ),
        ("keyword in root_cause", keyword_pass, f"keywords={expected['root_cause_keywords']}"),
    ]
    for label, passed, detail in checks:
        tag = "PASS" if passed else "FAIL"
        print(f"  [{tag}] {label:<26} {detail}")

    # ISSUES FOUND
    print(f"\n{DIV}")
    print("ISSUES FOUND")
    print(DIV)
    issues: list[str] = []
    if report.metadata.degraded:
        issues.append("Pipeline ran in DEGRADED mode -- one or more agents failed.")
    if not key_valid:
        issues.append(
            "ANTHROPIC_API_KEY is not configured (placeholder value detected). "
            "All LLM calls returned HTTP 401 Unauthorized -> degraded response. "
            "To get real LLM analysis set a valid key starting with 'sk-ant-'."
        )
    if report.metadata.total_cost_usd > orchestrator.MAX_COST_USD:
        issues.append(
            f"Cost ${report.metadata.total_cost_usd:.4f} exceeded "
            f"ceiling ${orchestrator.MAX_COST_USD}."
        )
    if not issues:
        issues.append("None -- pipeline completed successfully.")
    for issue in issues:
        print(f"  * {issue}")

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    asyncio.run(main())
