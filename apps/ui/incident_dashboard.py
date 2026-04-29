"""Premium Streamlit dashboard — AI Production Incident Debugger.

Run:
    streamlit run apps/ui/incident_dashboard.py

Backend must be running:
    uvicorn apps.api.main:app --reload
"""

from __future__ import annotations

import contextlib
import json
import time
from datetime import UTC, datetime

import requests
import streamlit as st

# ── Try plotly (optional) ──────────────────────────────────────────────────
try:
    import plotly.graph_objects as go

    _PLOTLY = True
except ImportError:
    _PLOTLY = False

API_URL = "http://127.0.0.1:8000/api/v1/incidents/analyze"
HEALTH_URL = "http://127.0.0.1:8000/docs"

_SEV_CFG: dict[str, dict] = {
    "CRITICAL": {
        "icon": "🔴",
        "color": "#ff4d6d",
        "bg": "rgba(255,77,109,.12)",
        "border": "rgba(255,77,109,.3)",
    },
    "HIGH": {
        "icon": "🟠",
        "color": "#ff8c42",
        "bg": "rgba(255,140,66,.12)",
        "border": "rgba(255,140,66,.3)",
    },
    "MEDIUM": {
        "icon": "🟡",
        "color": "#ffd166",
        "bg": "rgba(255,209,102,.12)",
        "border": "rgba(255,209,102,.3)",
    },
    "LOW": {
        "icon": "🟢",
        "color": "#06d6a0",
        "bg": "rgba(6,214,160,.12)",
        "border": "rgba(6,214,160,.3)",
    },
}

_SOURCE_CFG: dict[str, dict] = {
    "servicenow": {
        "label": "ServiceNow",
        "color": "#00c9a7",
        "bg": "rgba(0,201,167,.12)",
        "border": "rgba(0,201,167,.3)",
    },
    "dynatrace": {
        "label": "Dynatrace",
        "color": "#a78bfa",
        "bg": "rgba(167,139,250,.12)",
        "border": "rgba(167,139,250,.3)",
    },
}

_EXAMPLE = {
    "error_message": "HL7 ORU result failed in MuleSoft DataWeave transformation: missing OBX segment mapping",
    "stack_trace": (
        "Traceback (most recent call last):\n"
        '  File "/mulesoft/apps/lab-results-api/src/main/mule/lab-results-flow.xml", line 88, in transform-message\n'
        "DataWeaveMappingException: Cannot map OBX segment because OBX-3 observation identifier is missing"
    ),
    "logs": (
        "2026-04-28T10:12:00Z ERROR lab-results-api DataWeave transformation failed for HL7 ORU message\n"
        "2026-04-28T10:12:01Z WARN MuleSoft flow lis-to-ehr-oru failed in production\n"
        "2026-04-28T10:12:02Z ERROR Missing OBX segment mapping caused result not to post to EHR"
    ),
    "service_name": "lab-results-api",
    "environment": "production",
}

_ENV_OPTIONS = ["production", "staging", "development"]

# ══════════════════════════════════════════════════════════════════════════
# PAGE CONFIG  (must be first Streamlit call)
# ══════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Incident Debugger",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════════════════
# GLOBAL CSS
# ══════════════════════════════════════════════════════════════════════════
st.markdown(
    """
<style>
/* ── Reset / chrome ─────────────────────────────────────────── */
#MainMenu, footer, header, [data-testid="stToolbar"] { visibility:hidden; display:none; }
[data-testid="stAppViewContainer"] { background:#080c14; }
[data-testid="stSidebar"] > div:first-child {
    background:#0b0f1c;
    border-right:1px solid #1a2038;
    padding:24px 16px 16px;
}
[data-testid="stMainBlockContainer"] { padding:28px 32px 32px; }

/* ── Typography ─────────────────────────────────────────────── */
.t-page  { font-size:1.45rem; font-weight:800; color:#eef2ff; letter-spacing:-.03em; line-height:1.1; }
.t-sub   { font-size:.78rem;  color:#4a5380; margin-top:3px; }
.t-label { font-size:.65rem;  font-weight:700; color:#3a4468; text-transform:uppercase; letter-spacing:.14em; margin-bottom:8px; }
.t-body  { font-size:.93rem;  color:#c8d0e8; line-height:1.72; }
.t-mono  { font-family:monospace; font-size:.82rem; color:#7a85b0; }

/* ── Cards ──────────────────────────────────────────────────── */
.card {
    background:#0e1320;
    border:1px solid #1a2038;
    border-radius:12px;
    padding:18px 22px;
}
.card+.card { margin-top:10px; }

/* Accent left-border variants */
.ca-red    { border-left:3px solid #ff4d6d; }
.ca-orange { border-left:3px solid #ff8c42; }
.ca-yellow { border-left:3px solid #ffd166; }
.ca-green  { border-left:3px solid #06d6a0; }
.ca-blue   { border-left:3px solid #4f83ff; }
.ca-purple { border-left:3px solid #a78bfa; }
.ca-teal   { border-left:3px solid #2dd4bf; }
.ca-slate  { border-left:3px solid #64748b; }
.ca-amber  { border-left:3px solid #f59e0b; }

/* ── Severity badge ─────────────────────────────────────────── */
.badge {
    display:inline-flex; align-items:center; gap:7px;
    padding:5px 14px; border-radius:7px;
    font-size:.85rem; font-weight:700; letter-spacing:.05em;
}

/* ── KPI tile ───────────────────────────────────────────────── */
.kpi {
    background:#0e1320; border:1px solid #1a2038;
    border-radius:12px; padding:16px 18px;
    display:flex; flex-direction:column;
}
.kpi-val { font-size:1.65rem; font-weight:800; color:#eef2ff; line-height:1.1; }
.kpi-lbl { font-size:.63rem; font-weight:700; color:#3a4468;
           text-transform:uppercase; letter-spacing:.14em; margin-top:7px; }
.kpi-aux { font-size:.72rem; color:#2a3050; margin-top:3px; }

/* ── Validation steps ───────────────────────────────────────── */
.vstep { display:flex; gap:12px; padding:9px 0; border-bottom:1px solid #131a2e; align-items:flex-start; }
.vstep:last-child { border-bottom:none; }
.vstep-n {
    min-width:24px; height:24px; border-radius:50%;
    background:#162040; color:#4f83ff;
    display:flex; align-items:center; justify-content:center;
    font-size:.7rem; font-weight:800; flex-shrink:0; margin-top:2px;
}
.vstep-t { font-size:.88rem; color:#c8d0e8; line-height:1.55; }

/* ── Fix action items ───────────────────────────────────────── */
.fix-item { display:flex; gap:12px; padding:8px 0; border-bottom:1px solid #131a2e; align-items:flex-start; }
.fix-item:last-child { border-bottom:none; }
.fix-dot { min-width:8px; height:8px; border-radius:50%; background:#4f83ff; margin-top:6px; flex-shrink:0; }
.fix-dot-amber { background:#f59e0b; }
.fix-dot-green { background:#22c55e; }
.fix-t { font-size:.88rem; color:#c8d0e8; line-height:1.55; }

/* ── Agent trace table ──────────────────────────────────────── */
.atbl { width:100%; border-collapse:collapse; font-size:.84rem; }
.atbl th {
    text-align:left; padding:8px 12px;
    font-size:.62rem; font-weight:700; color:#2e3a5e;
    text-transform:uppercase; letter-spacing:.14em;
    border-bottom:1px solid #1a2038;
}
.atbl td { padding:10px 12px; color:#c8d0e8; border-bottom:1px solid #0f1525; vertical-align:middle; }
.atbl tr:last-child td { border-bottom:none; }
.atbl tr:hover td { background:#0c1222; }
.sdot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:7px; vertical-align:middle; flex-shrink:0; }
.sdot-ok  { background:#22c55e; box-shadow:0 0 6px rgba(34,197,94,.5); }
.sdot-err { background:#ef4444; box-shadow:0 0 6px rgba(239,68,68,.5); }
.sdot-unk { background:#4a5380; }
.mpill { background:#0f1e35; color:#60a5fa; padding:2px 8px; border-radius:4px; font-family:monospace; font-size:.76rem; }
.clat  { color:#38bdf8; font-family:monospace; font-size:.82rem; }
.ccost { color:#a78bfa; font-family:monospace; font-size:.82rem; }
.ctok  { color:#6ee7b7; font-family:monospace; font-size:.82rem; }
.cerr  { color:#f87171; font-size:.76rem; max-width:220px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block; }

/* ── Progress bar (latency) ─────────────────────────────────── */
.lbar-wrap { background:#0f1525; border-radius:3px; height:6px; min-width:60px; margin-top:4px; }
.lbar-fill { height:6px; border-radius:3px; background:linear-gradient(90deg,#38bdf8,#6366f1); }

/* ── Status pill ────────────────────────────────────────────── */
.pill-ok   { background:rgba(34,197,94,.1);  color:#4ade80; border:1px solid rgba(34,197,94,.25);  padding:3px 10px; border-radius:20px; font-size:.72rem; font-weight:600; }
.pill-warn { background:rgba(249,115,22,.1); color:#fb923c; border:1px solid rgba(249,115,22,.25); padding:3px 10px; border-radius:20px; font-size:.72rem; font-weight:600; }
.pill-err  { background:rgba(239,68,68,.1);  color:#f87171; border:1px solid rgba(239,68,68,.25);  padding:3px 10px; border-radius:20px; font-size:.72rem; font-weight:600; }

/* ── Banners ────────────────────────────────────────────────── */
.banner-warn { background:rgba(255,140,66,.08); border:1px solid rgba(255,140,66,.25); border-radius:10px; padding:11px 16px; color:#fdba74; font-size:.86rem; margin-bottom:10px; }
.banner-err  { background:rgba(255,77,109,.08); border:1px solid rgba(255,77,109,.25); border-radius:10px; padding:11px 16px; color:#fca5a5; font-size:.86rem; margin-bottom:10px; }
.banner-info { background:rgba(79,131,255,.08); border:1px solid rgba(79,131,255,.2);  border-radius:10px; padding:11px 16px; color:#93c5fd; font-size:.86rem; margin-bottom:10px; }

/* ── Divider ────────────────────────────────────────────────── */
.hdiv { border:none; border-top:1px solid #131a2e; margin:18px 0; }

/* ── Sidebar brand ──────────────────────────────────────────── */
.sb-brand { font-size:1.1rem; font-weight:800; color:#4f83ff; letter-spacing:-.02em; }
.sb-tag   { font-size:.7rem;  color:#2a3050; margin-top:1px; }
.sb-sec   { font-size:.62rem; font-weight:700; color:#2a3050; text-transform:uppercase; letter-spacing:.14em; margin:14px 0 5px; }
.sb-hint  { font-size:.72rem; color:#2a3050; text-align:center; margin-top:5px; }

/* ── Server status dot (sidebar) ────────────────────────────── */
.srv-dot  { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; }
.srv-on   { background:#22c55e; box-shadow:0 0 8px rgba(34,197,94,.6); }
.srv-off  { background:#ef4444; }
.srv-txt  { font-size:.72rem; color:#3a4468; vertical-align:middle; }

/* ── Loading animation ──────────────────────────────────────── */
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.agent-loading {
    display:flex; align-items:center; gap:10px;
    padding:10px 14px; border-radius:8px;
    background:#0e1320; border:1px solid #1a2038;
    margin-bottom:6px; font-size:.85rem; color:#8892b0;
}
.agent-loading .spin {
    width:14px; height:14px; border-radius:50%;
    border:2px solid #1a2038; border-top:2px solid #4f83ff;
    animation:spin .8s linear infinite; flex-shrink:0;
}
@keyframes spin { to { transform:rotate(360deg); } }
.agent-done  { color:#4ade80; }
.agent-queue { color:#2a3050; animation:pulse 2s ease-in-out infinite; }

/* ── Button overrides ───────────────────────────────────────── */
.stButton > button[kind="primary"] {
    background:linear-gradient(135deg,#1d4ed8,#6366f1) !important;
    border:none !important; border-radius:9px !important;
    font-weight:600 !important; height:42px !important;
    box-shadow:0 4px 16px rgba(99,102,241,.3) !important;
    transition:all .2s ease !important;
}
.stButton > button[kind="primary"]:hover {
    background:linear-gradient(135deg,#1e40af,#4f46e5) !important;
    box-shadow:0 6px 24px rgba(99,102,241,.5) !important;
    transform:translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
    background:transparent !important; border:1px solid #1a2038 !important;
    color:#4a5380 !important; border-radius:8px !important; height:36px !important;
}
[data-testid="stExpander"] {
    background:#0e1320 !important; border:1px solid #1a2038 !important;
    border-radius:10px !important;
}
[data-testid="stExpander"] summary {
    color:#4a5380 !important; font-size:.83rem !important;
}
.stTextArea textarea, .stTextInput > div > div > input {
    background:#080c14 !important; border-color:#1a2038 !important;
    color:#c8d0e8 !important; border-radius:8px !important;
    font-size:.86rem !important;
}
.stSelectbox > div > div {
    background:#080c14 !important; border-color:#1a2038 !important;
    border-radius:8px !important;
}
/* ── Tabs dark theme ────────────────────────────────────────── */
[data-baseweb="tab-list"] {
    background:#0b0f1c !important;
    border-bottom:1px solid #1a2038 !important;
    gap:4px;
}
[data-baseweb="tab"] {
    background:transparent !important;
    color:#3a4468 !important;
    font-size:.82rem !important;
    font-weight:600 !important;
    border-radius:8px 8px 0 0 !important;
    padding:8px 18px !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    background:#0e1320 !important;
    color:#eef2ff !important;
    border-bottom:2px solid #4f83ff !important;
}
[data-baseweb="tab-panel"] {
    background:#0b0f1c !important;
    padding:18px 0 0 !important;
}
/* ── Download button ────────────────────────────────────────── */
.stDownloadButton > button {
    background:#0e1320 !important;
    border:1px solid #1a2038 !important;
    color:#c8d0e8 !important;
    border-radius:9px !important;
    font-size:.84rem !important;
    font-weight:600 !important;
    width:100% !important;
    transition:all .2s ease !important;
}
.stDownloadButton > button:hover {
    border-color:#4f83ff !important;
    color:#93c5fd !important;
    background:#0c1222 !important;
}
</style>
""",
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════
# PRIMITIVE RENDER HELPERS
# ══════════════════════════════════════════════════════════════════════════


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def card(body: str, accent: str = "") -> None:
    cls = f"card ca-{accent}" if accent else "card"
    html(f'<div class="{cls}">{body}</div>')


def label(text: str) -> str:
    return f'<div class="t-label">{text}</div>'


def divider() -> None:
    html('<hr class="hdiv">')


def badge(severity: str) -> str:
    cfg = _SEV_CFG.get(
        severity,
        {
            "icon": "⚪",
            "color": "#8892b0",
            "bg": "rgba(136,146,176,.1)",
            "border": "rgba(136,146,176,.3)",
        },
    )
    return (
        f'<span class="badge" style="'
        f'background:{cfg["bg"]};color:{cfg["color"]};border:1px solid {cfg["border"]}">'
        f"{cfg['icon']} {severity}"
        f"</span>"
    )


def kpi_tile(value: str, label_text: str, aux: str = "", value_color: str = "#eef2ff") -> str:
    aux_html = f'<div class="kpi-aux">{aux}</div>' if aux else ""
    return (
        f'<div class="kpi">'
        f'<div class="kpi-val" style="color:{value_color}">{value}</div>'
        f'<div class="kpi-lbl">{label_text}</div>'
        f"{aux_html}</div>"
    )


def section_header(title: str) -> None:
    html(f'<div class="t-label" style="margin-bottom:10px">{title}</div>')


# ══════════════════════════════════════════════════════════════════════════
# DATA HELPERS
# ══════════════════════════════════════════════════════════════════════════


def _build_markdown_report(report: dict, payload: dict) -> str:
    svc = payload.get("service_name", "unknown")
    env = payload.get("environment", "production")
    inc_id = report.get("incident_id", "")
    severity = report.get("severity", "—")
    conf = report.get("confidence_score", 0.0)
    root_cause = report.get("root_cause", "")
    quick_fix = report.get("quick_fix", "")
    long_term_fix = report.get("long_term_fix", "")
    rollback_plan = report.get("rollback_plan", "")
    validation_steps = report.get("validation_steps", [])
    meta = report.get("metadata", {})
    traces = meta.get("agent_trace", [])
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    steps_md = "\n".join(f"{i}. {s}" for i, s in enumerate(validation_steps, 1))

    trace_rows = "\n".join(
        f"| {t.get('agent_name', '—')} | {t.get('status', '—')} | "
        f"{t.get('model_id', '—').split('-20')[0]} | "
        f"{t.get('latency_ms', 0):,.0f} ms | "
        f"${t.get('cost_usd', 0):.6f} |"
        for t in traces
    )
    trace_header = "| Agent | Status | Model | Latency | Cost |\n|---|---|---|---|---|"
    trace_section = f"{trace_header}\n{trace_rows}" if trace_rows else "_No trace available._"

    failure_reason = meta.get("failure_reason", "")
    degraded_note = ""
    if meta.get("degraded"):
        degraded_note = "\n> **Warning:** Pipeline ran in degraded mode — one or more agents failed.\n"
        if failure_reason:
            degraded_note += (
                f"> **Failure Reason:** {failure_reason}\n"
                "> System switched to safe fallback mode.\n"
            )

    return f"""# Incident Report

**Incident ID:** `{inc_id}`
**Service:** {svc}
**Environment:** {env}
**Severity:** {severity}
**Confidence:** {conf:.0%}
**Generated:** {ts}
{degraded_note}
---

## Root Cause

{root_cause}

---

## Remediation

### Immediate Fix

{quick_fix if quick_fix else "_No immediate fix available._"}

{"### Long-term Fix" + chr(10) + chr(10) + long_term_fix + chr(10) if long_term_fix else ""}
### Next Actions

{steps_md if steps_md else "_No validation steps provided._"}

### Rollback Plan

{rollback_plan if rollback_plan else "_No rollback plan provided._"}

---

## Pipeline Metadata

| Metric | Value |
|---|---|
| Total Cost | ${meta.get("total_cost_usd", 0):.5f} |
| Total Latency | {meta.get("total_latency_ms", 0):,.0f} ms |
| Pipeline Status | {"Degraded" if meta.get("degraded") else "Healthy"} |
| RAG Docs Retrieved | {meta.get("retrieved_docs_count", 0)} |

## Agent Trace

{trace_section}
"""


# ══════════════════════════════════════════════════════════════════════════
# SECTION RENDERERS
# ══════════════════════════════════════════════════════════════════════════


def render_report_header(report: dict, payload: dict) -> None:
    svc = payload.get("service_name", "unknown")
    env = payload.get("environment", "production")
    inc_id = report.get("incident_id", "")
    col_l, col_r = st.columns([3, 2])
    with col_l:
        html(
            f'<div class="t-page">Incident Analysis</div>'
            f'<div class="t-sub">{svc} &nbsp;·&nbsp; {env}</div>'
        )
    with col_r:
        html(
            f'<div style="text-align:right">'
            f'<div class="t-label" style="margin-bottom:4px">Incident ID</div>'
            f'<code style="background:#0e1320;border:1px solid #1a2038;'
            f'padding:4px 10px;border-radius:6px;font-size:.76rem;color:#4a5380;">'
            f"{inc_id}</code></div>"
        )
    divider()


def render_summary_kpis(report: dict, meta: dict) -> None:
    severity = report.get("severity", "HIGH")
    conf = report.get("confidence_score", 0.0)
    degraded = meta.get("degraded", False)
    cost = meta.get("total_cost_usd", 0.0)

    conf_color = "#22c55e" if conf >= 0.7 else ("#ffd166" if conf >= 0.4 else "#ff4d6d")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        html(kpi_tile(badge(severity), "Severity"))
    with c2:
        html(kpi_tile(f"{conf:.0%}", "Confidence", value_color=conf_color))
    with c3:
        status_val = (
            '<span class="pill-ok">✓ Healthy</span>'
            if not degraded
            else '<span class="pill-warn">⚠ Degraded</span>'
        )
        html(kpi_tile(status_val, "Pipeline Status"))
    with c4:
        html(kpi_tile(f"${cost:.5f}", "Total Cost", aux="ceiling $0.10"))


def render_root_cause(report: dict, severity: str) -> None:
    accent_map = {"CRITICAL": "red", "HIGH": "orange", "MEDIUM": "yellow", "LOW": "green"}
    section_header("Root Cause")
    card(
        f"{label('Analysis')}"
        f'<div class="t-body" style="margin-top:6px">{report.get("root_cause", "")}</div>',
        accent=accent_map.get(severity, "slate"),
    )


def render_remediation_tabs(report: dict) -> None:
    """Tabbed remediation section: Quick Fix | Long-term Fix | Next Actions | Rollback."""
    section_header("Remediation")

    quick_fix = report.get("quick_fix", "")
    long_term_fix = report.get("long_term_fix", "")
    rollback_plan = report.get("rollback_plan", "")
    validation_steps = report.get("validation_steps", [])

    tab_labels = ["⚡ Quick Fix", "🔭 Long-term Fix", "📋 Next Actions", "🔄 Rollback Plan"]
    t_quick, t_long, t_next, t_roll = st.tabs(tab_labels)

    with t_quick:
        if quick_fix:
            card(
                f"{label('Immediate Action')}"
                f'<div class="t-body" style="margin-top:6px">{quick_fix}</div>',
                accent="blue",
            )
        else:
            html('<div class="banner-info">No immediate fix available.</div>')

    with t_long:
        if long_term_fix:
            card(
                f"{label('Long-term Guidance')}"
                f'<div class="t-body" style="margin-top:6px">{long_term_fix}</div>',
                accent="amber",
            )
        else:
            html(
                '<div class="banner-info">'
                "No long-term fix returned. "
                "See <em>Next Actions</em> for follow-up steps."
                "</div>"
            )

    with t_next:
        if validation_steps:
            rows = "".join(
                f'<div class="vstep">'
                f'<div class="vstep-n">{i}</div>'
                f'<div class="vstep-t">{s}</div>'
                f"</div>"
                for i, s in enumerate(validation_steps, 1)
            )
            card(rows, accent="teal")
        else:
            html('<div class="banner-info">No validation steps provided.</div>')

    with t_roll:
        if rollback_plan:
            card(
                f"{label('Rollback Procedure')}"
                f'<div class="t-body" style="margin-top:6px">{rollback_plan}</div>',
                accent="purple",
            )
        else:
            html(
                '<div class="banner-warn">'
                "⚠ No rollback plan was returned. Follow standard runbook procedure."
                "</div>"
            )


def render_pipeline_metrics(meta: dict) -> None:
    section_header("Pipeline Metrics")
    m1, m2, m3, m4 = st.columns(4)
    models = meta.get("models_used", [])
    model_str = " · ".join(m.split("-20")[0] for m in models) if models else "—"
    with m1:
        html(kpi_tile(f"${meta.get('total_cost_usd', 0):.5f}", "Total Cost", aux="ceiling $0.10"))
    with m2:
        html(kpi_tile(f"{meta.get('total_latency_ms', 0):,.0f} ms", "Pipeline Latency"))
    with m3:
        html(kpi_tile(str(meta.get("retrieved_docs_count", 0)), "RAG Docs Retrieved"))
    with m4:
        html(kpi_tile(model_str, "Models", aux=f"{len(meta.get('agent_trace', []))} agents"))


def _latency_bar(ms: float, max_ms: float) -> str:
    pct = min(100, (ms / max_ms * 100)) if max_ms > 0 else 0
    return (
        f'<div class="clat">{ms:,.0f} ms</div>'
        f'<div class="lbar-wrap"><div class="lbar-fill" style="width:{pct:.0f}%"></div></div>'
    )


def render_agent_trace_table(traces: list[dict]) -> None:
    if not traces:
        html('<div class="banner-info">No agent trace available.</div>')
        return
    max_ms = max((t.get("latency_ms", 0) for t in traces), default=1)
    rows = ""
    for t in traces:
        ok = t.get("status") == "success"
        dot = "sdot-ok" if ok else ("sdot-err" if t.get("status") == "error" else "sdot-unk")
        err = t.get("error") or ""
        err_td = (
            f'<span class="cerr" title="{err}">{err[:70]}{"…" if len(err) > 70 else ""}</span>'
            if err
            else "—"
        )
        rows += (
            f"<tr>"
            f'<td><strong style="color:#eef2ff">{t["agent_name"]}</strong></td>'
            f'<td><span class="sdot {dot}"></span>{"success" if ok else t.get("status", "—")}</td>'
            f'<td><span class="mpill">{t["model_id"]}</span></td>'
            f"<td>{_latency_bar(t.get('latency_ms', 0), max_ms)}</td>"
            f'<td><span class="ctok">{t.get("input_tokens", 0):,}</span>'
            f' <span style="color:#2a3050">/</span> '
            f'<span class="ctok">{t.get("output_tokens", 0):,}</span></td>'
            f'<td><span class="ccost">${t.get("cost_usd", 0):.6f}</span></td>'
            f"<td>{err_td}</td>"
            f"</tr>"
        )
    html(
        '<div class="card">'
        '<table class="atbl"><thead><tr>'
        "<th>Agent</th><th>Status</th><th>Model</th>"
        "<th>Latency</th><th>In / Out Tokens</th><th>Cost</th><th>Error</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
    )


def render_charts(traces: list[dict]) -> None:
    if not traces or not _PLOTLY:
        return

    names = [t["agent_name"].replace("Agent", "") for t in traces]
    lats = [t.get("latency_ms", 0) for t in traces]
    costs = [t.get("cost_usd", 0) * 1000 for t in traces]
    statuses = [t.get("status", "") for t in traces]
    colors = ["#22c55e" if s == "success" else "#ef4444" for s in statuses]

    _CHART_LAYOUT = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#4a5380", size=11, family="system-ui"),
        hoverlabel=dict(bgcolor="#0e1320", bordercolor="#1a2038", font_color="#eef2ff"),
        showlegend=False,
    )
    _xaxis_bar = dict(
        showgrid=True, gridcolor="#131a2e", zeroline=False, color="#2a3050", title=None
    )
    _yaxis_bar = dict(showgrid=False, zeroline=False, color="#6b7280", autorange="reversed")

    col_lat, col_cost = st.columns(2)

    with col_lat:
        section_header("Agent Latency (ms)")
        fig_lat = go.Figure(
            go.Bar(
                x=lats,
                y=names,
                orientation="h",
                marker=dict(color=colors, opacity=0.85, line=dict(width=0)),
                text=[f"{v:,.0f} ms" for v in lats],
                textposition="outside",
                textfont=dict(color="#4a5380", size=10),
                hovertemplate="<b>%{y}</b><br>%{x:,.0f} ms<extra></extra>",
            )
        )
        fig_lat.update_layout(
            **_CHART_LAYOUT,
            height=220,
            margin=dict(l=10, r=10, t=32, b=10),
            xaxis=_xaxis_bar,
            yaxis=_yaxis_bar,
        )
        st.plotly_chart(fig_lat, width="stretch", config={"displayModeBar": False})

    with col_cost:
        section_header("Agent Cost (m$)")
        fig_cost = go.Figure(
            go.Bar(
                x=costs,
                y=names,
                orientation="h",
                marker=dict(
                    color=[
                        "rgba(167,139,250,.7)" if s == "success" else "rgba(239,68,68,.7)"
                        for s in statuses
                    ],
                    line=dict(width=0),
                ),
                text=[f"${v:.4f}m" for v in costs],
                textposition="outside",
                textfont=dict(color="#4a5380", size=10),
                hovertemplate="<b>%{y}</b><br>$%{x:.4f} m<extra></extra>",
            )
        )
        fig_cost.update_layout(
            **_CHART_LAYOUT,
            height=220,
            margin=dict(l=10, r=10, t=32, b=10),
            xaxis=_xaxis_bar,
            yaxis=_yaxis_bar,
        )
        st.plotly_chart(fig_cost, width="stretch", config={"displayModeBar": False})

    section_header("Agent Execution Timeline")
    cumulative, starts = 0.0, []
    for t in traces:
        starts.append(cumulative)
        cumulative += t.get("latency_ms", 0)

    fig_tl = go.Figure()
    for t, start in zip(traces, starts, strict=False):
        ms = t.get("latency_ms", 0)
        ok = t.get("status") == "success"
        name = t["agent_name"].replace("Agent", "")
        fig_tl.add_trace(
            go.Bar(
                x=[ms],
                y=[name],
                base=[start],
                orientation="h",
                marker=dict(
                    color="rgba(34,197,94,.75)" if ok else "rgba(239,68,68,.75)",
                    line=dict(width=0),
                    cornerradius=4,
                ),
                text=[f"{ms:,.0f} ms"],
                textposition="inside",
                textfont=dict(color="rgba(255,255,255,.8)", size=10),
                hovertemplate=f"<b>{name}</b><br>Start: %{{base:,.0f}} ms<br>Duration: {ms:,.0f} ms<extra></extra>",
                showlegend=False,
            )
        )

    fig_tl.update_layout(
        **_CHART_LAYOUT,
        height=200,
        barmode="overlay",
        margin=dict(l=10, r=10, t=32, b=30),
        xaxis=dict(
            showgrid=True,
            gridcolor="#131a2e",
            zeroline=False,
            color="#2a3050",
            title="Elapsed (ms)",
        ),
        yaxis=dict(showgrid=False, zeroline=False, color="#6b7280", autorange="reversed"),
    )
    st.plotly_chart(fig_tl, width="stretch", config={"displayModeBar": False})


def render_loading_animation() -> None:
    agents = ["PlannerAgent", "ClassifierAgent", "RootCauseAgent", "FixAgent", "CriticAgent"]
    html('<div class="t-label" style="margin-bottom:10px">Running Agent Pipeline</div>')
    for name in agents:
        html(
            f'<div class="agent-loading">'
            f'<div class="spin"></div>'
            f'<span class="agent-queue">{name}</span>'
            f"</div>"
        )


def render_rag_incidents(retrieved_docs: list[dict]) -> None:
    section_header("Retrieved Context from ServiceNow and Dynatrace")

    if not retrieved_docs:
        html(
            '<div class="banner-info">No similar past incidents retrieved from the knowledge base.</div>'
        )
        return

    total = len(retrieved_docs)
    html(
        f'<div class="t-sub" style="margin-bottom:14px;">'
        f"{total} document{'s' if total != 1 else ''} retrieved &nbsp;·&nbsp; "
        f"injected as RAG context into RootCauseAgent"
        f"</div>"
    )

    for idx, doc in enumerate(retrieved_docs, 1):
        raw_source = doc.get("source", "")
        description = doc.get("description", "No description available.")
        severity = doc.get("severity", "")
        score = doc.get("score", 0.0)
        score_pct = min(100, round(score * 100, 1))

        # ── Source pill ───────────────────────────────────────────────────
        src_cfg = _SOURCE_CFG.get(
            raw_source,
            {
                "label": raw_source or "unknown",
                "color": "#8892b0",
                "bg": "rgba(136,146,176,.1)",
                "border": "rgba(136,146,176,.3)",
            },
        )
        source_pill = (
            f'<span style="background:{src_cfg["bg"]};color:{src_cfg["color"]};'
            f"border:1px solid {src_cfg['border']};padding:3px 12px;border-radius:5px;"
            f'font-size:.70rem;font-weight:700;letter-spacing:.07em;text-transform:uppercase;">'
            f"{src_cfg['label']}</span>"
        )

        # ── Severity pill ─────────────────────────────────────────────────
        sev_cfg = _SEV_CFG.get(
            severity,
            {
                "icon": "⚪",
                "color": "#8892b0",
                "bg": "rgba(136,146,176,.1)",
                "border": "rgba(136,146,176,.3)",
            },
        )
        sev_icon = sev_cfg.get("icon", "")
        sev_pill = (
            f'<span style="background:{sev_cfg["bg"]};color:{sev_cfg["color"]};'
            f"border:1px solid {sev_cfg['border']};padding:3px 12px;border-radius:5px;"
            f'font-size:.70rem;font-weight:700;letter-spacing:.07em;">'
            f"{sev_icon} {severity}</span>"
            if severity
            else ""
        )

        # ── Card header: pills + index ────────────────────────────────────
        header_html = (
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;margin-bottom:12px;">'
            f'<div style="display:flex;gap:8px;flex-wrap:wrap;">'
            f"{source_pill}{sev_pill}"
            f"</div>"
            f'<span style="font-size:.68rem;color:#2a3050;font-family:monospace;">'
            f"#{idx} of {total}</span>"
            f"</div>"
        )

        # ── Labeled field rows ────────────────────────────────────────────
        _lbl = (
            'style="min-width:96px;font-size:.62rem;font-weight:700;color:#3a4468;'
            'text-transform:uppercase;letter-spacing:.12em;padding-top:3px;flex-shrink:0;"'
        )
        _val = 'style="flex:1;font-size:.88rem;color:#c8d0e8;line-height:1.6;"'
        _row_wrap = (
            'style="display:flex;gap:12px;padding:8px 0;'
            'border-bottom:1px solid #131a2e;align-items:flex-start;"'
        )

        source_row = (
            f'<div {_row_wrap}>'
            f'<div {_lbl}>Source</div>'
            f'<div {_val}><span class="t-mono">{raw_source or "—"}</span></div>'
            f"</div>"
        )
        desc_row = (
            f'<div {_row_wrap}>'
            f'<div {_lbl}>Description</div>'
            f'<div {_val}>{description}</div>'
            f"</div>"
        )
        sev_color = sev_cfg["color"]
        sev_row = (
            f'<div {_row_wrap}>'
            f'<div {_lbl}>Severity</div>'
            f'<div {_val}>'
            f'<span style="color:{sev_color};font-weight:700;">'
            f"{sev_icon} {severity if severity else '—'}"
            f"</span></div>"
            f"</div>"
        )

        # ── Similarity score (shown only when score > 0) ──────────────────
        if score > 0:
            score_color = (
                "#22c55e" if score_pct >= 70 else ("#ffd166" if score_pct >= 40 else "#ff4d6d")
            )
            score_section = (
                f'<div style="padding-top:10px;">'
                f'<div style="font-size:.62rem;font-weight:700;color:#3a4468;'
                f'text-transform:uppercase;letter-spacing:.12em;margin-bottom:7px;">'
                f"Similarity Score</div>"
                f'<div style="display:flex;align-items:center;gap:10px;">'
                f'<div style="flex:1;background:#0f1525;border-radius:3px;height:6px;">'
                f'<div style="width:{score_pct}%;height:6px;border-radius:3px;'
                f'background:linear-gradient(90deg,#4f83ff,#a78bfa);"></div>'
                f"</div>"
                f'<span style="font-size:.84rem;color:{score_color};font-family:monospace;'
                f'font-weight:700;min-width:46px;text-align:right;">{score_pct}%</span>'
                f'<span style="font-size:.68rem;color:#2a3050;">match</span>'
                f"</div>"
                f"</div>"
            )
        else:
            score_section = ""

        html(
            f'<div class="card ca-purple" style="margin-bottom:12px;">'
            f"{header_html}"
            f"{source_row}"
            f"{desc_row}"
            f"{sev_row}"
            f"{score_section}"
            f"</div>"
        )


def render_export_buttons(report: dict, payload: dict) -> None:
    """JSON and Markdown download buttons."""
    section_header("Export Report")

    inc_id = report.get("incident_id", "incident")[:8]
    svc = (payload.get("service_name") or "report").replace(" ", "-").lower()
    slug = f"{svc}-{inc_id}"

    json_bytes = json.dumps(report, indent=2).encode()
    md_bytes = _build_markdown_report(report, payload).encode()

    col_json, col_md, col_raw = st.columns([1, 1, 2])
    with col_json:
        st.download_button(
            label="⬇ Download JSON",
            data=json_bytes,
            file_name=f"incident-{slug}.json",
            mime="application/json",
            key="dl_json",
        )
    with col_md:
        st.download_button(
            label="⬇ Download Markdown",
            data=md_bytes,
            file_name=f"incident-{slug}.md",
            mime="text/markdown",
            key="dl_md",
        )


def render_raw_json(report: dict, traces: list[dict]) -> None:
    col_a, col_b = st.columns(2)
    with col_a, st.expander("Raw report JSON"):
        st.json(report)
    with col_b, st.expander("Agent trace JSON"):
        st.json(traces)


# ══════════════════════════════════════════════════════════════════════════
# SERVER HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════


@st.cache_data(ttl=10)
def _server_up() -> bool:
    try:
        return requests.get(HEALTH_URL, timeout=2).status_code < 500
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════
# API CALL
# ══════════════════════════════════════════════════════════════════════════


def call_api(payload: dict) -> dict | None:
    try:
        r = requests.post(API_URL, json=payload, timeout=120)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        html(
            '<div class="banner-err">'
            "🔌 <strong>Cannot reach the backend.</strong> "
            'Start it with: <code style="background:#1a1020;padding:1px 6px;border-radius:3px">'
            "uvicorn apps.api.main:app --reload</code>"
            "</div>"
        )
        return None
    except requests.exceptions.Timeout:
        html('<div class="banner-warn">⏱ Request timed out after 120 s. Try again.</div>')
        return None
    except requests.exceptions.HTTPError as exc:
        detail = ""
        with contextlib.suppress(Exception):
            detail = exc.response.json().get("detail", "")
        html(f'<div class="banner-err">⚠ HTTP {exc.response.status_code}: {detail or exc}</div>')
        return None
    except Exception as exc:
        html(f'<div class="banner-err">Unexpected error: {exc}</div>')
        return None


# ══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    html(
        '<div class="sb-brand">🔍 Incident Debugger</div>'
        '<div class="sb-tag">Multi-agent AI · Claude pipeline</div>'
    )
    html('<hr class="hdiv">')

    if st.button("⚡ Load example", width="stretch", key="btn_example"):
        for k, v in _EXAMPLE.items():
            st.session_state[f"ex_{k}"] = v

    html('<div class="sb-sec">Incident Details</div>')

    error_message = st.text_area(
        "Error Message *",
        value=st.session_state.get("ex_error_message", ""),
        height=68,
        placeholder="e.g. DataWeaveMappingException: Cannot map OBX segment …",
    )
    stack_trace = st.text_area(
        "Stack Trace *",
        value=st.session_state.get("ex_stack_trace", ""),
        height=130,
        placeholder="Traceback (most recent call last): …",
    )
    logs = st.text_area(
        "Logs *",
        value=st.session_state.get("ex_logs", ""),
        height=100,
        placeholder="2026-04-28T10:12:01Z ERROR …",
    )

    html('<div class="sb-sec">Context</div>')

    service_name = st.text_input(
        "Service Name",
        value=st.session_state.get("ex_service_name", ""),
        placeholder="e.g. lab-results-api",
    )
    _env_default = st.session_state.get("ex_environment", "production")
    _env_idx = _ENV_OPTIONS.index(_env_default) if _env_default in _ENV_OPTIONS else 0
    environment = st.selectbox("Environment", _ENV_OPTIONS, index=_env_idx)

    html('<hr class="hdiv">')

    ready = bool(error_message.strip() and stack_trace.strip() and logs.strip())
    analyze = st.button("Analyze Incident →", type="primary", width="stretch", disabled=not ready)
    if not ready:
        html('<div class="sb-hint">Fill in error, stack trace, and logs.</div>')

    html('<hr class="hdiv">')

    up = _server_up()
    dot_cls = "srv-on" if up else "srv-off"
    srv_text = "Backend connected" if up else "Backend offline"
    html(
        f'<div style="display:flex;align-items:center;gap:0">'
        f'<span class="srv-dot {dot_cls}"></span>'
        f'<span class="srv-txt">{srv_text}</span>'
        f"</div>"
    )


# ══════════════════════════════════════════════════════════════════════════
# MAIN PANEL — EMPTY STATE
# ══════════════════════════════════════════════════════════════════════════

if not analyze:
    html("""
    <div style="margin:60px auto 0;max-width:540px;text-align:center">
      <div style="font-size:2.8rem;margin-bottom:14px">🔍</div>
      <div style="font-size:1.5rem;font-weight:800;color:#eef2ff;letter-spacing:-.02em">
        Healthcare MuleSoft Order &amp; Result Incident Debugger
      </div>
      <div style="font-size:.92rem;color:#3a4468;margin-top:10px;line-height:1.65">
        Paste an error, stack trace, and logs in the sidebar.<br>
        A 5-agent Claude pipeline returns root cause, fix, and rollback in under 60 s.
      </div>
      <div style="display:flex;gap:14px;justify-content:center;margin-top:28px;flex-wrap:wrap">
        <div style="background:#0e1320;border:1px solid #1a2038;border-radius:10px;padding:14px 22px">
          <div style="font-size:1.4rem;font-weight:800;color:#4f83ff">5</div>
          <div style="font-size:.62rem;color:#2a3050;text-transform:uppercase;letter-spacing:.12em;margin-top:4px">Agents</div>
        </div>
        <div style="background:#0e1320;border:1px solid #1a2038;border-radius:10px;padding:14px 22px">
          <div style="font-size:1.4rem;font-weight:800;color:#a78bfa">RAG</div>
          <div style="font-size:.62rem;color:#2a3050;text-transform:uppercase;letter-spacing:.12em;margin-top:4px">Context</div>
        </div>
        <div style="background:#0e1320;border:1px solid #1a2038;border-radius:10px;padding:14px 22px">
          <div style="font-size:1.4rem;font-weight:800;color:#06d6a0">$0.10</div>
          <div style="font-size:.62rem;color:#2a3050;text-transform:uppercase;letter-spacing:.12em;margin-top:4px">Cost Ceiling</div>
        </div>
        <div style="background:#0e1320;border:1px solid #1a2038;border-radius:10px;padding:14px 22px">
          <div style="font-size:1.4rem;font-weight:800;color:#38bdf8">&lt;60s</div>
          <div style="font-size:.62rem;color:#2a3050;text-transform:uppercase;letter-spacing:.12em;margin-top:4px">Latency</div>
        </div>
      </div>
    </div>
    """)
    st.stop()


# ══════════════════════════════════════════════════════════════════════════
# MAIN PANEL — ANALYSIS
# ══════════════════════════════════════════════════════════════════════════

payload: dict = {
    "error_message": error_message.strip(),
    "stack_trace": stack_trace.strip(),
    "logs": logs.strip(),
    "environment": environment,
}
if service_name.strip():
    payload["service_name"] = service_name.strip()

# Loading state
loading_slot = st.empty()
with loading_slot.container():
    render_loading_animation()

with st.spinner(""):
    t0 = time.monotonic()
    report = call_api(payload)
    elapsed = time.monotonic() - t0

loading_slot.empty()

if report is None:
    st.stop()

meta = report.get("metadata", {})
severity = report.get("severity", "HIGH")
traces = meta.get("agent_trace", [])

# ── Degraded banner ────────────────────────────────────────────────────────
if meta.get("degraded"):
    failure_reason = meta.get("failure_reason")
    failure_section = ""
    if failure_reason:
        failure_section = (
            '<div style="margin-top:10px;padding-top:10px;'
            'border-top:1px solid rgba(255,140,66,.2);">'
            '<span style="font-size:.68rem;font-weight:700;text-transform:uppercase;'
            'letter-spacing:.12em;color:#f97316;">Failure Reason</span>'
            f'<div style="margin-top:4px;font-size:.85rem;color:#fdba74;">{failure_reason}</div>'
            '<div style="margin-top:6px;font-size:.80rem;color:#fb923c;">'
            "⟳ System switched to safe fallback mode"
            "</div>"
            "</div>"
        )
    html(
        '<div class="banner-warn">'
        "⚠️ <strong>Degraded mode</strong> — one or more agents failed. "
        "Fallback defaults were used; results may have lower accuracy."
        f"{failure_section}"
        "</div>"
    )

# ── Header ──────────────────────────────────────────────────────────────────
render_report_header(report, payload)

# ── 4-column KPIs ───────────────────────────────────────────────────────────
render_summary_kpis(report, meta)

html("<br>")

# ── Root cause ───────────────────────────────────────────────────────────────
render_root_cause(report, severity)

html("<br>")

# ── Tabbed remediation: Quick Fix | Long-term | Next Actions | Rollback ──────
render_remediation_tabs(report)

divider()

# ── Export ───────────────────────────────────────────────────────────────────
render_export_buttons(report, payload)

divider()

# ── Pipeline metrics (collapsible) ────────────────────────────────────────────
with st.expander("📊 Pipeline Metrics & Cost", expanded=False):
    render_pipeline_metrics(meta)
    if _PLOTLY and traces:
        html("<br>")
        render_charts(traces)
    elif not _PLOTLY and traces:
        html(
            '<div class="banner-info">Install <code>plotly</code> for latency, '
            "cost, and timeline charts: <code>pip install plotly</code></div>"
        )

# ── Agent trace (collapsible) ─────────────────────────────────────────────────
with st.expander("🤖 Agent Trace", expanded=False):
    render_agent_trace_table(traces)

divider()

# ── Similar past incidents (RAG) ───────────────────────────────────────────────
retrieved_docs = meta.get("retrieved_docs", [])
render_rag_incidents(retrieved_docs)

divider()

# ── Raw JSON (collapsible) ─────────────────────────────────────────────────────
render_raw_json(report, traces)
