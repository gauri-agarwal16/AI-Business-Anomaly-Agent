"""
anomaly.py
----------
Statistical anomaly detection. This module is the single source of truth for
"is this an anomaly, and how severe is it". The LLM (llm.py) is NEVER allowed
to make this call — it only explains anomalies that this module has already
detected, using the evidence this module produces.

Method, per date, for the overall time series of a metric (optionally filtered
to a single dimension slice for driver analysis):
  1. Build a rolling baseline (mean + std) from the N periods BEFORE the current one.
  2. pct_change = (current - baseline_mean) / baseline_mean * 100
  3. z_score = (current - baseline_mean) / baseline_std
  4. Flag as anomaly only if BOTH the pct_change and z_score thresholds are cleared.
     (Using both avoids flagging noisy-but-small-magnitude series on z-score alone,
     and avoids flagging naturally-volatile series on pct-change alone.)
  5. Severity is assigned from configurable magnitude bands on |pct_change|.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd

from config import (
    DEFAULT_PCT_CHANGE_THRESHOLD,
    DEFAULT_ZSCORE_THRESHOLD,
    DEFAULT_ROLLING_WINDOW,
    MIN_HISTORY_POINTS,
    SEVERITY_THRESHOLDS,
    METRIC_DIRECTION,
)


@dataclass
class AnomalyPoint:
    date: pd.Timestamp
    metric: str
    actual_value: float
    baseline_mean: float
    baseline_std: float
    pct_change: float
    z_score: float
    direction: str          # "UP" or "DOWN"
    is_good_or_bad: str     # "GOOD" or "BAD" — direction translated via METRIC_DIRECTION
    severity: str            # "NORMAL" | "LOW" | "MEDIUM" | "HIGH"
    is_anomaly: bool


def _severity_from_pct(abs_pct_change: float) -> str:
    """Map an absolute percentage deviation to a severity band.
    Bands are checked from highest to lowest so a 60% move lands in HIGH, not LOW."""
    if abs_pct_change >= SEVERITY_THRESHOLDS["HIGH"]:
        return "HIGH"
    if abs_pct_change >= SEVERITY_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    if abs_pct_change >= SEVERITY_THRESHOLDS["LOW"]:
        return "LOW"
    return "NORMAL"


def _direction_label(metric: str, direction: str) -> str:
    """Translate a raw UP/DOWN movement into GOOD/BAD business terms using config."""
    orientation = METRIC_DIRECTION.get(metric, "higher_is_better")
    if orientation == "higher_is_better":
        return "GOOD" if direction == "UP" else "BAD"
    return "BAD" if direction == "UP" else "GOOD"


def detect_anomalies(
    series_df: pd.DataFrame,
    metric: str,
    date_col: str = "date",
    rolling_window: int = DEFAULT_ROLLING_WINDOW,
    pct_change_threshold: float = DEFAULT_PCT_CHANGE_THRESHOLD,
    zscore_threshold: float = DEFAULT_ZSCORE_THRESHOLD,
) -> pd.DataFrame:
    """
    Run anomaly detection over a single metric's time series.

    series_df must already be aggregated to one row per date (use
    aggregate_daily() below first if the raw data has dimension rows).

    Returns a DataFrame of AnomalyPoint rows (one per date), including NORMAL points,
    so the caller can plot the full trend and highlight only the anomalous points.
    """
    df = series_df[[date_col, metric]].dropna(subset=[metric]).sort_values(date_col).reset_index(drop=True)

    results = []
    for i in range(len(df)):
        current_date = df.loc[i, date_col]
        current_value = float(df.loc[i, metric])

        window_start = max(0, i - rolling_window)
        history = df.loc[window_start:i - 1, metric]  # strictly prior periods only

        if len(history) < min(MIN_HISTORY_POINTS, rolling_window):
            # Not enough history yet to trust a baseline — record as NORMAL/insufficient data.
            results.append(AnomalyPoint(
                date=current_date, metric=metric, actual_value=current_value,
                baseline_mean=np.nan, baseline_std=np.nan, pct_change=np.nan,
                z_score=np.nan, direction="N/A", is_good_or_bad="N/A",
                severity="NORMAL", is_anomaly=False,
            ))
            continue

        baseline_mean = float(history.mean())
        baseline_std = float(history.std(ddof=0)) or 1e-9  # avoid div-by-zero on flat history

        pct_change = ((current_value - baseline_mean) / baseline_mean * 100) if baseline_mean != 0 else 0.0
        z_score = (current_value - baseline_mean) / baseline_std

        direction = "UP" if current_value >= baseline_mean else "DOWN"
        good_or_bad = _direction_label(metric, direction)

        clears_pct = abs(pct_change) >= pct_change_threshold
        clears_z = abs(z_score) >= zscore_threshold
        is_anomaly = clears_pct and clears_z

        severity = _severity_from_pct(abs(pct_change)) if is_anomaly else "NORMAL"

        results.append(AnomalyPoint(
            date=current_date, metric=metric, actual_value=current_value,
            baseline_mean=baseline_mean, baseline_std=baseline_std,
            pct_change=round(pct_change, 2), z_score=round(z_score, 2),
            direction=direction, is_good_or_bad=good_or_bad,
            severity=severity, is_anomaly=is_anomaly,
        ))

    return pd.DataFrame([r.__dict__ for r in results])


def aggregate_daily(df: pd.DataFrame, metric: str, date_col: str = "date") -> pd.DataFrame:
    """Collapse a raw (possibly multi-dimension) DataFrame down to one row per date
    by summing the metric across all dimensions. This is the series anomaly
    detection runs on at the top level."""
    return (
        df.groupby(date_col, as_index=False)[metric]
        .sum()
        .sort_values(date_col)
        .reset_index(drop=True)
    )
