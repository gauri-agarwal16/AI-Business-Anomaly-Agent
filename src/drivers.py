"""
drivers.py
----------
Given an anomaly already confirmed by anomaly.py on the TOTAL series for a metric
and date, this module answers: "which dimension slices (region/category/product/
customer_segment) and which related metrics moved the most, and in the same
direction as the overall anomaly?"

Important: this module only reports OBSERVED statistical movement per slice. It
does not claim causation — that framing distinction is enforced again in llm.py's
prompt, but the data itself here is kept strictly factual (a number and a % change).
"""

import pandas as pd

from src.anomaly import aggregate_daily, detect_anomalies
from config import DEFAULT_ROLLING_WINDOW


def analyze_dimension_drivers(
    raw_df: pd.DataFrame,
    metric: str,
    anomaly_date: pd.Timestamp,
    dimension_cols: list,
    date_col: str = "date",
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    top_n: int = 5,
) -> dict:
    """
    For each available dimension column, find which values (e.g. which region)
    contributed most to the metric's movement on anomaly_date, by running the
    same baseline-comparison logic per-slice and ranking by absolute pct_change
    weighted by that slice's share of total volume.

    Returns: {dimension_name: [ {value, actual, baseline_mean, pct_change, direction}, ... ]}
    """
    driver_results = {}

    for dim in dimension_cols:
        if dim not in raw_df.columns:
            continue

        slice_rows = []
        for value, group in raw_df.groupby(dim):
            daily = aggregate_daily(group, metric, date_col)
            if anomaly_date not in set(daily[date_col]):
                continue

            detected = detect_anomalies(
                daily, metric, date_col=date_col, rolling_window=rolling_window,
                # Loosen thresholds to 0 here: for driver ranking we want the RAW
                # pct_change/z_score per slice regardless of whether that slice alone
                # clears the anomaly bar — the total-series anomaly already happened.
                pct_change_threshold=0, zscore_threshold=0,
            )
            row = detected[detected[date_col] == anomaly_date]
            if row.empty or pd.isna(row.iloc[0]["pct_change"]):
                continue

            r = row.iloc[0]
            slice_rows.append({
                "value": value,
                "actual": round(float(r["actual_value"]), 2),
                "baseline_mean": round(float(r["baseline_mean"]), 2),
                "pct_change": float(r["pct_change"]),
                "direction": r["direction"],
            })

        # Rank by magnitude of movement — biggest movers first.
        slice_rows.sort(key=lambda x: abs(x["pct_change"]), reverse=True)
        driver_results[dim] = slice_rows[:top_n]

    return driver_results


def analyze_related_metric_drivers(
    raw_df: pd.DataFrame,
    primary_metric: str,
    anomaly_date: pd.Timestamp,
    date_col: str = "date",
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
) -> dict:
    """
    Checks related metrics that mechanically explain movement in the primary metric:
      - revenue  <-> orders, average_order_value (revenue / orders)
      - profit   <-> revenue, profit_margin (profit / revenue)
      - orders   <-> customers, cancellations

    Returns {related_metric_name: {actual, baseline_mean, pct_change, direction}}
    """
    related = {}

    def _pct_for(metric_name: str):
        if metric_name not in raw_df.columns:
            return None
        daily = aggregate_daily(raw_df, metric_name, date_col)
        detected = detect_anomalies(
            daily, metric_name, date_col=date_col, rolling_window=rolling_window,
            pct_change_threshold=0, zscore_threshold=0,
        )
        row = detected[detected[date_col] == anomaly_date]
        if row.empty or pd.isna(row.iloc[0]["pct_change"]):
            return None
        r = row.iloc[0]
        return {
            "actual": round(float(r["actual_value"]), 2),
            "baseline_mean": round(float(r["baseline_mean"]), 2),
            "pct_change": float(r["pct_change"]),
            "direction": r["direction"],
        }

    # Direct related metrics present in the data
    candidate_map = {
        "revenue": ["orders", "profit", "returns", "cancellations"],
        "orders": ["customers", "cancellations", "returns"],
        "profit": ["revenue", "orders"],
        "customers": ["orders", "cancellations"],
        "returns": ["orders", "revenue"],
        "cancellations": ["orders", "revenue"],
    }
    for m in candidate_map.get(primary_metric, []):
        result = _pct_for(m)
        if result:
            related[m] = result

    # Derived ratio: average order value, only when both revenue & orders exist.
    if {"revenue", "orders"}.issubset(raw_df.columns) and primary_metric in ("revenue", "orders"):
        daily = raw_df.groupby(date_col, as_index=False)[["revenue", "orders"]].sum()
        daily["average_order_value"] = daily["revenue"] / daily["orders"].replace(0, pd.NA)
        detected = detect_anomalies(
            daily, "average_order_value", date_col=date_col, rolling_window=rolling_window,
            pct_change_threshold=0, zscore_threshold=0,
        )
        row = detected[detected[date_col] == anomaly_date]
        if not row.empty and not pd.isna(row.iloc[0]["pct_change"]):
            r = row.iloc[0]
            related["average_order_value"] = {
                "actual": round(float(r["actual_value"]), 2),
                "baseline_mean": round(float(r["baseline_mean"]), 2),
                "pct_change": float(r["pct_change"]),
                "direction": r["direction"],
            }

    return related
