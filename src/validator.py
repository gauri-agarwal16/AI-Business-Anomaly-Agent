"""
validator.py
------------
Validates a loaded DataFrame BEFORE any statistical analysis runs.

Design decision: we distinguish ERRORS (analysis cannot safely proceed) from
WARNINGS (analysis can proceed, but the user should know rows were dropped or
data looks thin). The caller (app.py) decides how to react to each.
"""

from dataclasses import dataclass, field
import pandas as pd

from src.loader import KNOWN_METRICS
from config import MIN_HISTORY_POINTS


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    cleaned_df: pd.DataFrame = None
    available_metrics: list = field(default_factory=list)


def validate(df: pd.DataFrame) -> ValidationResult:
    errors = []
    warnings = []

    # --- Structural checks -------------------------------------------------
    if "date" not in df.columns:
        errors.append("Missing required 'date' column.")
        return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

    available_metrics = [c for c in KNOWN_METRICS if c in df.columns]
    if not available_metrics:
        errors.append(
            f"No recognized metric columns found. Expected at least one of: {KNOWN_METRICS}"
        )
        return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

    cleaned = df.copy()

    # --- Row-level checks ----------------------------------------------------
    n_before = len(cleaned)
    bad_date_mask = cleaned["date"].isna()
    if bad_date_mask.any():
        warnings.append(
            f"Dropped {int(bad_date_mask.sum())} row(s) with unparseable or missing 'date' values."
        )
        cleaned = cleaned[~bad_date_mask]

    # A row with ALL metric columns missing is useless for analysis.
    all_metrics_missing = cleaned[available_metrics].isna().all(axis=1)
    if all_metrics_missing.any():
        warnings.append(
            f"Dropped {int(all_metrics_missing.sum())} row(s) with no values in any metric column."
        )
        cleaned = cleaned[~all_metrics_missing]

    # Negative values in metrics that should logically never be negative.
    non_negative_metrics = ["revenue", "orders", "profit_margin", "customers", "returns", "cancellations"]
    for col in [c for c in non_negative_metrics if c in cleaned.columns]:
        neg_mask = cleaned[col] < 0
        if neg_mask.any():
            warnings.append(
                f"Column '{col}' has {int(neg_mask.sum())} negative value(s); "
                f"they were kept but may indicate a data entry error."
            )

    # Duplicate (date, dimension-combo) rows can double count in aggregation.
    dim_cols = [c for c in ["region", "category", "product", "customer_segment"] if c in cleaned.columns]
    dedup_keys = ["date"] + dim_cols
    dup_mask = cleaned.duplicated(subset=dedup_keys, keep=False)
    if dup_mask.any():
        warnings.append(
            f"Found {int(dup_mask.sum())} duplicate row(s) for the same date/dimension combination. "
            f"They were kept as-is; consider whether they should be summed or de-duplicated upstream."
        )

    if len(cleaned) == 0:
        errors.append("No usable rows remained after cleaning.")
        return ValidationResult(is_valid=False, errors=errors, warnings=warnings)

    # --- Volume checks -------------------------------------------------------
    n_dates = cleaned["date"].nunique()
    if n_dates < MIN_HISTORY_POINTS:
        warnings.append(
            f"Only {n_dates} distinct date(s) found (minimum recommended: {MIN_HISTORY_POINTS}). "
            f"Baseline/z-score results will be low-confidence or skipped until more history is available."
        )

    cleaned = cleaned.sort_values("date").reset_index(drop=True)

    return ValidationResult(
        is_valid=True,
        errors=errors,
        warnings=warnings,
        cleaned_df=cleaned,
        available_metrics=available_metrics,
    )
