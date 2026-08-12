"""
loader.py
---------
Responsible for ONE thing: getting an uploaded Excel file into a clean pandas
DataFrame with normalized column names and typed values. It does not judge whether
the data is "good enough" to analyze — that's validator.py's job.
"""

import pandas as pd


# Columns we recognize as business metrics if present. Anything else in the file
# that isn't a known metric or dimension is treated as an unrecognized column
# (kept, but ignored by anomaly detection).
KNOWN_METRICS = ["revenue", "orders", "profit", "customers", "returns", "cancellations"]
KNOWN_DIMENSIONS = ["region", "category", "product", "customer_segment"]
REQUIRED_COLUMNS = ["date"]


def load_excel(file) -> pd.DataFrame:
    """
    Load an Excel file (path or file-like object, e.g. a Streamlit UploadedFile)
    into a DataFrame with normalized, lowercase, underscore-separated column names.

    Raises:
        ValueError: if the file can't be parsed as Excel at all.
    """
    try:
        df = pd.read_excel(file, engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"Could not read Excel file: {exc}") from exc

    df = _normalize_columns(df)
    df = _coerce_types(df)
    return df


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase, strip, and underscore column headers so 'Customer Segment' ==
    'customer_segment' regardless of how the user typed it in Excel."""
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    return df


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Convert the date column to datetime and known metric columns to numeric,
    coercing unparseable values to NaN (validator.py decides what to do with those)."""
    df = df.copy()

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in KNOWN_METRICS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in KNOWN_DIMENSIONS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    return df


def detect_available_metrics(df: pd.DataFrame) -> list:
    """Return the known metric columns that are actually present in this file."""
    return [c for c in KNOWN_METRICS if c in df.columns]


def detect_available_dimensions(df: pd.DataFrame) -> list:
    """Return the known dimension columns that are actually present in this file."""
    return [c for c in KNOWN_DIMENSIONS if c in df.columns]
