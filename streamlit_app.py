from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from analytics_agent.agent import AnalyticsAgent
from analytics_agent.governed_tools import METRICS
from analytics_agent.trusted_layer import RAW_DB, TRUSTED_DB
from analytics_agent.ui_helpers import (
    chart_rows,
    format_delta,
    format_metric_value,
    metric_label,
    quality_label,
)


EXAMPLE_QUESTIONS = [
    "Why did Web visits increase in January?",
    "Compare March visitor conversion by country",
    "Compare March visit conversion by country",
    "March gross revenue by country",
    "As of 2026-05-11, how did March net revenue compare with February?",
    "Is iOS checkout tracking available from 2026-03-15 to 2026-03-18?",
    "How many visits occurred in 2025?",
]


st.set_page_config(
    page_title="Auditable Ecommerce Analytics Agent",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root { --ink:#172033; --muted:#657187; --line:#e3e8ef; --blue:#315efb; }
      .stApp { background: #f7f9fc; color: var(--ink); }
      [data-testid="stSidebar"] { background: #101827; }
      [data-testid="stSidebar"] * { color: #edf2f7; }
      [data-testid="stSidebar"] .stSelectbox label { color:#aab6c8; }
      .block-container { max-width: 1220px; padding-top: 2rem; padding-bottom: 4rem; }
      .hero { background:linear-gradient(135deg,#111b2f,#243b67); color:white;
              border-radius:18px; padding:28px 32px; margin-bottom:18px; }
      .hero h1 { margin:0 0 8px; font-size:2rem; letter-spacing:-0.03em; }
      .hero p { margin:0; max-width:820px; color:#cbd5e1; font-size:1rem; }
      .eyebrow { color:#83a7ff; font-size:.78rem; font-weight:700; letter-spacing:.12em;
                 text-transform:uppercase; margin-bottom:8px; }
      .status { display:inline-flex; align-items:center; gap:7px; padding:5px 11px;
                border-radius:999px; font-size:.78rem; font-weight:700; }
      .status-trusted { background:#e8f7ef; color:#166534; }
      .status-adjusted { background:#fff4dc; color:#92400e; }
      .status-unavailable { background:#feecec; color:#991b1b; }
      .definition { border-left:3px solid var(--blue); padding:8px 14px; color:var(--muted);
                    margin:10px 0 18px; background:white; border-radius:0 8px 8px 0; }
      .flag { border:1px solid #f1d59a; background:#fff9eb; border-radius:10px;
              padding:13px 15px; margin:8px 0; }
      .flag strong { color:#7c4a03; }
      [data-testid="stMetric"] { background:white; border:1px solid var(--line);
                                 border-radius:12px; padding:14px 16px; }
      div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:10px; }
      .small-note { color:var(--muted); font-size:.84rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner="Building the governed analytics layer…")
def get_agent() -> AnalyticsAgent:
    if not RAW_DB.exists():
        from generator.generate_data import generate

        generate(seed=42, n_users=10_000, n_days=120)
    return AnalyticsAgent(TRUSTED_DB)


def status_badge(status: str) -> None:
    st.markdown(
        f'<span class="status status-{status}">● {quality_label(status)}</span>',
        unsafe_allow_html=True,
    )


def render_headline(answer: dict) -> None:
    metric = answer["request"]["metric"]
    rows = answer.get("result") or []
    comparison = {row["segment"]: row for row in answer.get("comparison_summary") or []}

    if not rows:
        st.error("No metric value was returned because the request did not pass the data-availability gate.")
        return

    columns = st.columns(min(len(rows), 4))
    for index, row in enumerate(rows):
        delta = format_delta(metric, comparison[row["segment"]]) if row["segment"] in comparison else None
        columns[index % len(columns)].metric(
            label=str(row["segment"]).upper() if row["segment"] != "all" else metric_label(metric),
            value=format_metric_value(metric, row.get("value")),
            delta=delta,
        )

    plotted = chart_rows(answer)
    if len(plotted) > 1 or answer.get("comparison_summary"):
        frame = pd.DataFrame(plotted).set_index("segment")
        display_columns = [column for column in ("comparison", "current") if column in frame]
        st.bar_chart(frame[display_columns], color=["#9aa9c2", "#315efb"][: len(display_columns)])


def render_quality_flags(answer: dict) -> None:
    flags = answer["presentation"]["data_quality_flags"]
    policy_flags = answer["presentation"]["policy_flags"]
    if not flags and not policy_flags:
        st.success("No metric-specific data-quality or policy exceptions were found for this request.")
        return

    for flag in flags:
        period = " to ".join(filter(None, [flag.get("start_date"), flag.get("end_date")]))
        impact = flag.get("blocked_or_adjusted_value")
        impact_text = f" Impact: {impact:,}." if isinstance(impact, (int, float)) else ""
        st.markdown(
            f'<div class="flag"><strong>{period or "Affected period"}</strong><br>'
            f'{flag.get("situation", "Data-quality issue")}. '
            f'Treatment: {flag.get("treatment", "reviewed")}.{impact_text}</div>',
            unsafe_allow_html=True,
        )
    for flag in policy_flags:
        st.markdown(
            '<div class="flag"><strong>Fraud policy applied</strong><br>'
            f'Confirmed fraud excluded: {flag["confirmed_excluded_order_count"]:,} orders. '
            f'Suspected or unconfirmed fraud retained and flagged: {flag["suspected_included_order_count"]:,} orders.'
            '</div>',
            unsafe_allow_html=True,
        )


def render_investigation(answer: dict) -> None:
    investigation = answer.get("investigation")
    if not investigation:
        st.info("Ask a question using “why”, “increase”, “decrease”, or “change” to trigger bounded investigation evidence.")
        return
    left, right = st.columns([1, 2])
    left.caption("Classification")
    left.markdown(f"**{investigation['classification'].replace('_', ' ').title()}**")
    left.metric("Confidence", investigation["confidence"].title())
    right.markdown("**Recommended next action**")
    right.write(investigation["recommended_action"])
    right.caption("Temporal overlap is presented as context, not causal proof.")

    evidence = investigation["evidence"]
    if evidence.get("campaigns"):
        st.markdown("**Overlapping campaign context**")
        st.dataframe(pd.DataFrame(evidence["campaigns"]), width="stretch", hide_index=True)
    if evidence.get("app_releases"):
        st.markdown("**Overlapping release context**")
        st.dataframe(pd.DataFrame(evidence["app_releases"]), width="stretch", hide_index=True)


def render_evidence(answer: dict) -> None:
    result = answer.get("result") or []
    if result:
        st.markdown("#### Reviewed result rows")
        st.dataframe(pd.DataFrame(result), width="stretch", hide_index=True)
    st.markdown("#### Sources")
    st.write(" · ".join(f"`{source}`" for source in answer["sources"]))
    if answer["limitations"]:
        st.markdown("#### Limitations")
        for limitation in answer["limitations"]:
            st.markdown(f"- {limitation}")


def render_sql_and_trace(answer: dict) -> None:
    for label, query in answer["executed_queries"].items():
        if not query:
            continue
        with st.expander(f"{label.title()} governed SQL", expanded=label == "current"):
            st.code(query["sql"].strip(), language="sql")
            st.caption(f"Parameters: {json.dumps(query['parameters'])}")
    st.markdown("#### Execution trace")
    st.dataframe(pd.DataFrame(answer["trace"]), width="stretch", hide_index=True)
    st.caption(f"Query policy: {answer['query_policy']}")


with st.sidebar:
    st.markdown("## Demo controls")
    selected_example = st.selectbox("Try a governed question", EXAMPLE_QUESTIONS)
    if st.button("Use this example", width="stretch"):
        st.session_state.question = selected_example
    st.markdown("---")
    st.markdown("**Supported metrics**")
    for spec in METRICS.values():
        st.caption(f"• {spec.label}")
    st.markdown("---")
    st.caption("Synthetic ecommerce data · Jan–Apr 2026 · deterministic MVP")


st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Product analytics · reliability-first</div>
      <h1>Auditable Ecommerce Analytics Agent</h1>
      <p>Ask a business question. The agent returns a governed metric, visible data-quality treatment,
      and the exact evidence trail behind the answer.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if "question" not in st.session_state:
    st.session_state.question = EXAMPLE_QUESTIONS[0]

with st.form("question_form"):
    question = st.text_area(
        "Ask the analytics agent",
        key="question",
        height=88,
        help="Supported periods are January–April 2026. Net Revenue requires an explicit as-of date.",
    )
    submitted = st.form_submit_button("Run governed analysis", type="primary", width="stretch")

if "answer" not in st.session_state:
    submitted = True

if submitted:
    try:
        with st.spinner("Validating the request and running governed tools…"):
            st.session_state.answer = get_agent().answer(question)
            st.session_state.last_question = question
        st.rerun()
    except ValueError as error:
        st.session_state.pop("answer", None)
        st.error(str(error))
    except Exception as error:
        st.session_state.pop("answer", None)
        st.error(f"The governed analysis could not run: {error}")

answer = st.session_state.get("answer")
if answer:
    st.markdown(f"### {metric_label(answer['request']['metric'])}")
    status_badge(answer["quality_status"])
    st.markdown(f'<div class="definition">{answer["metric_definition"]}</div>', unsafe_allow_html=True)

    answer_tab, quality_tab, evidence_tab, audit_tab = st.tabs(
        ["Answer", "Quality & policy", "Evidence", "SQL & trace"]
    )
    with answer_tab:
        render_headline(answer)
        st.markdown("#### Investigation")
        render_investigation(answer)
    with quality_tab:
        render_quality_flags(answer)
    with evidence_tab:
        render_evidence(answer)
    with audit_tab:
        render_sql_and_trace(answer)

    st.markdown(
        '<p class="small-note">The MVP uses deterministic intent parsing and governed, read-only SQL. '
        'It abstains when coverage or metric-health requirements fail.</p>',
        unsafe_allow_html=True,
    )
