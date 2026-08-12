"""
email_alert.py
--------------
Sends email alerts via SMTP for anomalies that clear the configured severity bar.
Credentials always come from environment variables (see config.py / .env.example) —
never hard-coded here.

This module also enforces the "no duplicate alerts" requirement by checking
alert_history before sending, and always recording the outcome after.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import (
    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
    ALERT_EMAIL_FROM, ALERT_EMAIL_TO, ALERT_SEVERITIES,
)
from src.alert_history import already_alerted, record_alert


def build_subject(metric: str, severity: str) -> str:
    return f"{severity} {metric.capitalize()} Anomaly Detected"


def build_body(evidence: dict, summary: dict) -> str:
    lines = [
        f"Metric: {evidence['metric']}",
        f"Date: {evidence['date']}",
        f"Actual value: {evidence['actual_value']}",
        f"Expected (baseline): {evidence['expected_value_baseline']}",
        f"Deviation: {evidence['deviation_percent']:+.1f}%",
        f"Z-score: {evidence['z_score']}",
        f"Severity: {evidence['severity']}",
        "",
        "WHAT HAPPENED",
        summary["what_happened"],
        "",
        "OBSERVED DRIVERS",
        summary["observed_drivers"],
        "",
        "SIGNIFICANCE",
        summary["significance"],
        "",
        "INVESTIGATE NEXT",
        summary["investigate_next"],
    ]
    return "\n".join(lines)


def send_email(subject: str, body: str, to_addresses: list) -> tuple:
    """Send a plain-text email via SMTP. Returns (success: bool, message: str)."""
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        return False, "SMTP credentials are not configured (set SMTP_USERNAME / SMTP_PASSWORD)."
    if not to_addresses:
        return False, "No recipient configured (set ALERT_EMAIL_TO)."

    msg = MIMEMultipart()
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = ", ".join(to_addresses)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(ALERT_EMAIL_FROM, to_addresses, msg.as_string())
        return True, "Email sent successfully."
    except Exception as exc:
        return False, f"Failed to send email: {exc}"


def process_alert(evidence: dict, summary: dict) -> dict:
    """
    Full alert pipeline for one confirmed anomaly:
      1. Skip entirely if severity doesn't require alerting.
      2. Skip if we've already alerted on this metric+date+direction (dedup).
      3. Otherwise attempt to send, then record the outcome either way.

    Returns a status dict for display in the UI.
    """
    metric = evidence["metric"]
    date = evidence["date"]
    severity = evidence["severity"]
    direction = evidence["direction"]

    if severity not in ALERT_SEVERITIES:
        return {"status": "skipped", "reason": f"Severity '{severity}' is below the alerting threshold."}

    if already_alerted(metric, date, direction):
        return {"status": "skipped", "reason": "An alert for this metric and date was already sent previously."}

    to_addresses = [a.strip() for a in ALERT_EMAIL_TO.split(",") if a.strip()]
    subject = build_subject(metric, severity)
    body = build_body(evidence, summary)

    success, message = send_email(subject, body, to_addresses)

    record_alert(
        metric=metric, anomaly_date=date, severity=severity, direction=direction,
        pct_change=evidence["deviation_percent"], z_score=evidence["z_score"],
        summary=summary["what_happened"], emailed=success,
    )

    return {"status": "sent" if success else "failed", "reason": message}