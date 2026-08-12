"""
config.py
---------
Single source of truth for all configurable behavior in the Anomaly Monitoring Agent.

Nothing in anomaly.py, drivers.py, email_alert.py, etc. should hard-code a threshold,
a file path, or a secret. They import from here instead. This makes the whole system
tunable without touching detection logic, and keeps secrets out of source control.
"""

import os
from dotenv import load_dotenv

# Load variables from a local .env file (never committed to source control).
load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "alert_history.db")

# ---------------------------------------------------------------------------
# Anomaly detection thresholds (defaults — all overridable from the Streamlit UI)
# ---------------------------------------------------------------------------
# Minimum absolute percentage change vs. the historical baseline to even be considered.
DEFAULT_PCT_CHANGE_THRESHOLD = 20.0

# Minimum absolute z-score vs. the rolling mean/std to be considered statistically unusual.
DEFAULT_ZSCORE_THRESHOLD = 2.0

# Rolling window (in periods) used to compute the historical baseline mean/std.
DEFAULT_ROLLING_WINDOW = 7

# Minimum number of historical data points required before we trust a baseline at all.
MIN_HISTORY_POINTS = 5

# Severity bands, expressed as minimum ABSOLUTE percentage deviation from baseline.
# A data point must ALSO clear the z-score threshold to be flagged at all (see anomaly.py);
# these bands only decide how severe an already-flagged anomaly is.
SEVERITY_THRESHOLDS = {
    "LOW": 20.0,
    "MEDIUM": 30.0,
    "HIGH": 50.0,
}

# Whether higher values are "good" for a metric. This changes how we describe direction
# in business terms (e.g., a revenue drop is bad, but a "returns" drop is good) without
# changing the underlying statistics — detection is symmetric either way.
METRIC_DIRECTION = {
    "revenue": "higher_is_better",
    "orders": "higher_is_better",
    "profit": "higher_is_better",
    "customers": "higher_is_better",
    "returns": "lower_is_better",
    "cancellations": "lower_is_better",
}

# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------
# Only these severities will trigger an email alert.
ALERT_SEVERITIES = {"MEDIUM", "HIGH"}

# ---------------------------------------------------------------------------
# Secrets / external services (all pulled from environment variables — never hard-code)
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", SMTP_USERNAME)
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")  # comma-separated list of recipients
