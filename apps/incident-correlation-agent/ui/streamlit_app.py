"""
Streamlit UI — Incident Correlation Agent
Run: streamlit run ui/streamlit_app.py
"""

import os

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Incident Correlation Agent",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 Incident Correlation Agent")
st.caption("Correlates ServiceNow incidents with Dynatrace problems — powered by Claude AI")


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")
    state_filter = st.multiselect(
        "Incident State",
        options={"1": "New", "2": "In Progress", "3": "On Hold"}.items(),
        default=[("1", "New"), ("2", "In Progress")],
        format_func=lambda x: f"{x[1]} ({x[0]})",
    )
    limit = st.slider("Max incidents", min_value=5, max_value=100, value=20)
    refresh = st.button("Refresh", use_container_width=True)


state_codes = ",".join(s[0] for s in state_filter) if state_filter else "1,2"


# ── Fetch correlated incidents ────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def get_correlated(state: str, limit: int):
    resp = requests.get(
        f"{API_BASE}/incidents/correlated/all",
        params={"state": state, "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


if refresh:
    st.cache_data.clear()

try:
    with st.spinner("Fetching incidents and Dynatrace problems..."):
        correlated = get_correlated(state_codes, limit)
except Exception as exc:
    st.error(f"Failed to fetch data: {exc}")
    st.stop()


# ── Summary metrics ───────────────────────────────────────────────────────────
total = len(correlated)
matched = sum(1 for c in correlated if c["matched_problems"])
high_priority = sum(1 for c in correlated if c["incident"]["priority"].startswith(("1", "2")))

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Incidents", total)
col2.metric("Correlated with DT", matched)
col3.metric("High Priority", high_priority)
col4.metric("Unmatched", total - matched)

st.divider()


# ── Incident table ────────────────────────────────────────────────────────────
st.subheader("Open Incidents")

STATE_LABELS = {"1": "New", "2": "In Progress", "3": "On Hold", "6": "Resolved", "7": "Closed"}
PRIORITY_COLORS = {"1": "🔴", "2": "🟠", "3": "🟡", "4": "🔵", "5": "⚪"}

rows = []
for c in correlated:
    inc = c["incident"]
    pcolor = PRIORITY_COLORS.get(str(inc["priority"])[0], "⚪")
    rows.append(
        {
            "": pcolor,
            "Number": inc["number"],
            "Summary": inc["short_description"][:80],
            "Priority": inc["priority"],
            "State": STATE_LABELS.get(str(inc["state"]), inc["state"]),
            "Service/CI": inc.get("cmdb_ci") or "—",
            "DT Problems": len(c["matched_problems"]),
            "Score": c["correlation_score"],
        }
    )

if rows:
    st.dataframe(rows, use_container_width=True, hide_index=True)


# ── Incident detail + AI analysis ────────────────────────────────────────────
st.divider()
st.subheader("Incident Detail + AI Root Cause Analysis")

incident_numbers = [c["incident"]["number"] for c in correlated]
selected = st.selectbox("Select incident to analyze", options=incident_numbers)

if selected and st.button("Run AI Analysis", type="primary"):
    with st.spinner("AI agent analyzing incident and traces..."):
        try:
            resp = requests.post(f"{API_BASE}/analysis/incident/{selected}", timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")
            st.stop()

    corr = data["correlation"]
    analysis = data.get("analysis")
    inc = corr["incident"]

    # Incident info
    with st.expander("ServiceNow Incident Details", expanded=True):
        c1, c2, c3 = st.columns(3)
        c1.metric("Number", inc["number"])
        c2.metric("Priority", inc["priority"])
        c3.metric("State", STATE_LABELS.get(str(inc["state"]), inc["state"]))
        st.markdown(f"**Summary:** {inc['short_description']}")
        if inc.get("description"):
            st.markdown(f"**Description:** {inc['description']}")
        st.markdown(f"**Service/CI:** `{inc.get('cmdb_ci') or 'N/A'}`")
        opened = inc.get("opened_at", "N/A")
        st.markdown(f"**Opened:** {opened}")

    # Dynatrace problems
    if corr["matched_problems"]:
        with st.expander(
            f"Correlated Dynatrace Problems ({len(corr['matched_problems'])})", expanded=True
        ):
            for p in corr["matched_problems"]:
                st.markdown(f"**{p['displayId']}** — {p['title']}")
                st.markdown(
                    f"Severity: `{p['severityLevel']}`"
                    f" | Impact: `{p['impactLevel']}`"
                    f" | Status: `{p['status']}`"
                )
                if p.get("service_names"):
                    st.markdown(f"Services: {', '.join(p['service_names'])}")
                st.divider()

    # Correlation reasons
    if corr["correlation_reasons"]:
        with st.expander("Correlation Reasons"):
            for r in corr["correlation_reasons"]:
                st.markdown(f"- {r}")

    # AI analysis
    if analysis:
        st.subheader("AI Root Cause Analysis")
        conf_color = {"HIGH": "green", "MEDIUM": "orange", "LOW": "red"}.get(
            analysis["confidence"], "grey"
        )
        st.markdown(f"**Confidence:** :{conf_color}[{analysis['confidence']}]")

        st.markdown("### Root Cause")
        st.info(analysis["root_cause_summary"])

        if analysis["contributing_factors"]:
            st.markdown("### Contributing Factors")
            for f in analysis["contributing_factors"]:
                st.markdown(f"- {f}")

        st.markdown("### Suggested Resolution")
        st.success(analysis["suggested_resolution"])

        if analysis["recommended_actions"]:
            st.markdown("### Recommended Actions")
            for i, a in enumerate(analysis["recommended_actions"], 1):
                st.markdown(f"{i}. {a}")

        if analysis["related_services"]:
            st.markdown("### Related Services")
            st.markdown(", ".join(f"`{s}`" for s in analysis["related_services"]))
    else:
        st.warning("AI analysis was not available for this incident.")
