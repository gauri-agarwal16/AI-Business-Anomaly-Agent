"""
app.py
------
Streamlit front-end for the Business Anomaly Monitoring Agent.

Flow:
  1. Upload Excel -> loader.py
  2. Validate -> validator.py (show errors/warnings)
  3. Pick metric + thresholds -> anomaly.py detects anomalies on the total series
  4. Show KPI cards + trend chart with anomalies highlighted
  5. Pick a specific detected anomaly -> drivers.py breaks it down
  6. Generate an AI summary from that evidence -> llm.py
  7. Optionally trigger an email alert -> email_alert.py (severity-gated + deduped)
  8. View alert history -> alert_history.py
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from src.loader import load_excel, detect_available_metrics, detect_available_dimensions
from src.validator import validate
from src.anomaly import aggregate_daily, detect_anomalies
from src.drivers import analyze_dimension_drivers, analyze_related_metric_drivers
from src.llm import build_evidence_payload, generate_summary
from src.email_alert import process_alert
from src.alert_history import get_alert_history
from config import DEFAULT_PCT_CHANGE_THRESHOLD, DEFAULT_ZSCORE_THRESHOLD, DEFAULT_ROLLING_WINDOW

st.set_page_config(page_title="Business Anomaly Monitoring Agent", layout="wide")
st.title("📊 Business Anomaly Monitoring Agent")
st.caption("Upload business data → detect anomalies statistically → explain them with AI → alert on the ones that matter.")

# ---------------------------------------------------------------------------
# Sidebar: thresholds (configurable, not hard-coded)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Detection Settings")
    pct_threshold = st.slider("Percentage change threshold (%)", 5, 100, int(DEFAULT_PCT_CHANGE_THRESHOLD))
    z_threshold = st.slider("Z-score threshold", 1.0, 4.0, float(DEFAULT_ZSCORE_THRESHOLD), step=0.1)
    rolling_window = st.slider("Rolling baseline window (periods)", 3, 30, DEFAULT_ROLLING_WINDOW)
    st.divider()
    st.caption("An anomaly is flagged only when BOTH thresholds are exceeded on the SAME date.")

# ---------------------------------------------------------------------------
# Step 1: Upload
# ---------------------------------------------------------------------------
uploaded_file = st.file_uploader("Upload a standardized Excel file (.xlsx)", type=["xlsx"])

if uploaded_file is None:
    st.info("Upload an Excel file to begin, or use the sample file in `data/sample_sales_data.xlsx`.")
    st.stop()

try:
    raw_df = load_excel(uploaded_file)
except ValueError as e:
    st.error(str(e))
    st.stop()

# ---------------------------------------------------------------------------
# Step 2: Validate
# ---------------------------------------------------------------------------
result = validate(raw_df)

if result.warnings:
    with st.expander(f"⚠️ {len(result.warnings)} data warning(s)", expanded=False):
        for w in result.warnings:
            st.warning(w)

if not result.is_valid:
    for e in result.errors:
        st.error(e)
    st.stop()

df = result.cleaned_df
available_metrics = result.available_metrics
available_dimensions = detect_available_dimensions(df)

with st.expander("Preview cleaned data", expanded=False):
    st.dataframe(df.head(50), use_container_width=True)

# ---------------------------------------------------------------------------
# Step 3: Metric selection + detection
# ---------------------------------------------------------------------------
col_a, col_b = st.columns([1, 3])
with col_a:
    metric = st.selectbox("Metric to analyze", available_metrics)

daily = aggregate_daily(df, metric)
detected = detect_anomalies(
    daily, metric,
    rolling_window=rolling_window,
    pct_change_threshold=pct_threshold,
    zscore_threshold=z_threshold,
)
anomalies_only = detected[detected["is_anomaly"]].sort_values("date", ascending=False)

# ---------------------------------------------------------------------------
# Step 4: KPI cards
# ---------------------------------------------------------------------------
latest = detected.dropna(subset=["pct_change"]).iloc[-1] if detected.dropna(subset=["pct_change"]).shape[0] else None
k1, k2, k3, k4 = st.columns(4)
k1.metric("Latest value", f"{daily[metric].iloc[-1]:,.0f}")
k2.metric("Latest deviation", f"{latest['pct_change']:+.1f}%" if latest is not None else "N/A")
k3.metric("Total anomalies found", f"{len(anomalies_only)}")
k4.metric("High severity count", f"{(anomalies_only['severity'] == 'HIGH').sum()}")

# ---------------------------------------------------------------------------
# Step 5: Trend chart with anomaly highlighting
# ---------------------------------------------------------------------------
fig = go.Figure()
fig.add_trace(go.Scatter(x=detected["date"], y=detected["actual_value"], mode="lines+markers", name=metric, line=dict(color="#4C78A8")))
if not anomalies_only.empty:
    colors = anomalies_only["severity"].map({"LOW": "#F2C744", "MEDIUM": "#F58518", "HIGH": "#E45756"})
    fig.add_trace(go.Scatter(
        x=anomalies_only["date"], y=anomalies_only["actual_value"], mode="markers",
        marker=dict(size=12, color=colors, line=dict(width=1, color="black")),
        name="Anomaly", text=anomalies_only["severity"], hovertemplate="%{x}<br>%{y}<br>Severity: %{text}",
    ))
fig.update_layout(title=f"{metric.capitalize()} trend with detected anomalies", height=420, hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Step 6: Anomaly table + selection
# ---------------------------------------------------------------------------
st.subheader("Detected Anomalies")
if anomalies_only.empty:
    st.success("No anomalies detected for this metric at the current thresholds.")
    st.stop()

display_cols = ["date", "actual_value", "baseline_mean", "pct_change", "z_score", "direction", "is_good_or_bad", "severity"]
st.dataframe(anomalies_only[display_cols], use_container_width=True, hide_index=True)

anomalies_only = anomalies_only.reset_index(drop=True)
options = [f"{row.date.date()} — {row.severity} ({row.pct_change:+.1f}%)" for row in anomalies_only.itertuples()]
selected_idx = st.selectbox("Select an anomaly to investigate", range(len(options)), format_func=lambda i: options[i])
selected_row = anomalies_only.iloc[selected_idx]

# ---------------------------------------------------------------------------
# Step 7: Driver analysis + AI summary
# ---------------------------------------------------------------------------
st.subheader("Driver Analysis & AI Summary")

if st.button("🔍 Analyze drivers and generate AI summary", type="primary"):
    with st.spinner("Analyzing contributing dimensions and related metrics..."):
        dim_drivers = analyze_dimension_drivers(
            df, metric, selected_row["date"], available_dimensions, rolling_window=rolling_window
        )
        related_drivers = analyze_related_metric_drivers(
            df, metric, selected_row["date"], rolling_window=rolling_window
        )
        evidence = build_evidence_payload(selected_row.to_dict(), dim_drivers, related_drivers)

    with st.spinner("Generating AI business summary from evidence..."):
        summary = generate_summary(evidence)

    st.session_state["evidence"] = evidence
    st.session_state["summary"] = summary

if "evidence" in st.session_state and "summary" in st.session_state:
    evidence = st.session_state["evidence"]
    summary = st.session_state["summary"]

    with st.expander("Structured evidence sent to the LLM", expanded=False):
        st.json(evidence)

    st.markdown("#### What Happened")
    st.write(summary["what_happened"])
    st.markdown("#### Observed Drivers")
    st.write(summary["observed_drivers"])
    st.markdown("#### Significance")
    st.write(summary["significance"])
    st.markdown("#### What to Investigate Next")
    st.write(summary["investigate_next"])

    st.divider()
    st.markdown(f"**Severity:** {evidence['severity']} — email alerts are only sent for MEDIUM/HIGH severity, and only once per metric+date.")
    if st.button("📧 Trigger email alert for this anomaly"):
        with st.spinner("Processing alert..."):
            outcome = process_alert(evidence, summary)
        if outcome["status"] == "sent":
            st.success(outcome["reason"])
        elif outcome["status"] == "skipped":
            st.info(outcome["reason"])
        else:
            st.error(outcome["reason"])

# ---------------------------------------------------------------------------
# Step 8: Alert history
# ---------------------------------------------------------------------------
st.subheader("Alert History")
history = get_alert_history()
if history:
    hist_df = pd.DataFrame(history)[["created_at", "metric", "anomaly_date", "severity", "direction", "pct_change", "z_score", "emailed", "summary"]]
    st.dataframe(hist_df, use_container_width=True, hide_index=True)
else:
    st.caption("No alerts recorded yet.")
