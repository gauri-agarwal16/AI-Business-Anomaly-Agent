"""
alert_history.py
-----------------
Persists a record of every alert we've sent (or decided to send) to SQLite, and
uses that history to prevent duplicate notifications for the same metric+date+direction.

Table: alerts
  id INTEGER PRIMARY KEY
  metric TEXT
  anomaly_date TEXT   (ISO date, e.g. "2026-07-15")
  severity TEXT
  direction TEXT NOT NULL
  pct_change REAL
  z_score REAL
  summary TEXT         -- the "what_happened" line, for quick reference in history views
  emailed INTEGER       -- 1 if an email was actually sent, 0 if suppressed/logged only
  created_at TEXT
"""

import sqlite3
from datetime import datetime, timezone

from config import DB_PATH


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric TEXT NOT NULL,
            anomaly_date TEXT NOT NULL,
            severity TEXT NOT NULL,
            direction TEXT NOT NULL,
            pct_change REAL,
            z_score REAL,
            summary TEXT,
            emailed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(metric, anomaly_date, direction)
        )
    """)
    return conn


def already_alerted(metric: str, anomaly_date: str, direction: str) -> bool:
    """True if we have a prior record for this metric+date+direction."""
    conn = _connect()
    try:
        cur = conn.execute(
            """
            SELECT 1
            FROM alerts
            WHERE metric = ? AND anomaly_date = ? AND direction = ?
            LIMIT 1
            """,
            (metric, str(anomaly_date), direction),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


def record_alert(
    metric: str,
    anomaly_date: str,
    severity: str,
    direction: str,
    pct_change: float,
    z_score: float,
    summary: str,
    emailed: bool,
) -> None:
    """Insert a new alert record."""
    conn = _connect()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO alerts
               (metric, anomaly_date, severity, direction, pct_change,
                z_score, summary, emailed, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                metric,
                str(anomaly_date),
                severity,
                direction,
                pct_change,
                z_score,
                summary,
                1 if emailed else 0,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_alert_history(limit: int = 100):
    """Return recent alert records, most recent first, as a list of dicts."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
