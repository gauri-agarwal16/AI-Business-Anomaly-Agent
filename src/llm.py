"""
llm.py
------
Turns structured, already-computed evidence (from anomaly.py + drivers.py) into a
plain-English business summary.

Hard rule enforced by design: the LLM is given NUMBERS ONLY, never raw data or the
ability to re-derive whether something is anomalous. The severity, direction, and
anomaly status are already decided before this module is ever called. The prompt
explicitly forbids inventing causes not present in the evidence, and requires the
model to separate "observed drivers" (statistically correlated movement we measured)
from "possible causes" (plausible business explanations it may suggest, clearly
labeled as speculation, not fact).
"""

import json
from openai import OpenAI

from config import OPENAI_API_KEY, LLM_MODEL

SYSTEM_PROMPT = """You are a business data analyst assistant. You will be given
STRUCTURED EVIDENCE about a single detected business metric anomaly: the metric,
its actual vs. expected (baseline) value, percentage deviation, statistical
significance, severity, and any related metrics or dimension slices (e.g. region,
category, product) that also moved on the same date.

Rules you MUST follow:
1. Use ONLY the evidence provided. Do not invent numbers, events, or causes that are
   not in the evidence (e.g. do not mention a "promotion" or "outage" unless the
   evidence says so).
2. Anomaly detection has ALREADY been performed statistically. Do not re-evaluate,
   question, or override whether this is an anomaly — treat it as a given fact.
3. Clearly separate two things in your answer:
   - "Observed drivers": dimensions/metrics that the evidence shows moved in a
     statistically correlated way. State these as measured facts with their numbers.
   - "Possible causes to investigate": plausible business explanations for WHY those
     drivers moved. These are hypotheses, not facts — label them explicitly as such
     and keep them generic/operational (e.g. "check for a pricing or promotion change
     in the affected region") rather than inventing a specific unverified event.
4. Be concise and business-appropriate. No jargon, no hedging filler.

Respond ONLY with a JSON object with exactly these keys (all string values):
{
  "what_happened": "...",
  "observed_drivers": "...",
  "significance": "...",
  "investigate_next": "..."
}
Return nothing else — no markdown fences, no preamble.
"""


def build_evidence_payload(anomaly_row: dict, dimension_drivers: dict, related_metric_drivers: dict) -> dict:
    """Assemble the exact structured evidence object that will be sent to the LLM.
    Keeping this as an explicit, inspectable function makes it easy to prove (e.g. in
    an interview) that only computed evidence — never raw rows — reaches the model."""
    return {
        "metric": anomaly_row["metric"],
        "date": str(anomaly_row["date"]),
        "actual_value": anomaly_row["actual_value"],
        "expected_value_baseline": anomaly_row["baseline_mean"],
        "deviation_percent": anomaly_row["pct_change"],
        "z_score": anomaly_row["z_score"],
        "direction": anomaly_row["direction"],
        "is_good_or_bad_for_business": anomaly_row["is_good_or_bad"],
        "severity": anomaly_row["severity"],
        "dimension_drivers": dimension_drivers,
        "related_metric_drivers": related_metric_drivers,
    }


def generate_summary(evidence: dict) -> dict:
    """
    Calls the LLM with the structured evidence and returns a dict with keys:
    what_happened, observed_drivers, significance, investigate_next.

    Falls back to a deterministic, template-based summary (no LLM call) if no API
    key is configured, so the rest of the app remains usable/demoable without one.
    """
    if not OPENAI_API_KEY:
        return _fallback_summary(evidence)

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(evidence, default=str)},
            ],
        )
        content = response.choices[0].message.content.strip()
        return json.loads(content)
    except Exception as exc:
        fallback = _fallback_summary(evidence)
        fallback["what_happened"] += f" (Note: LLM call failed, using fallback summary — {exc})"
        return fallback


def _fallback_summary(evidence: dict) -> dict:
    """A deterministic, template-based summary used when no LLM is available.
    Still follows the observed-vs-possible distinction using only evidence data."""
    metric = evidence["metric"]
    pct = evidence["deviation_percent"]
    direction_word = "increased" if evidence["direction"] == "UP" else "decreased"
    good_bad = evidence["is_good_or_bad_for_business"].lower()

    driver_bits = []
    for dim, entries in evidence.get("dimension_drivers", {}).items():
        for e in entries[:2]:
            driver_bits.append(f"{dim}={e['value']} ({e['pct_change']:+.1f}%)")
    for m, e in evidence.get("related_metric_drivers", {}).items():
        driver_bits.append(f"{m} ({e['pct_change']:+.1f}%)")
    drivers_text = "; ".join(driver_bits) if driver_bits else "No dimension or related-metric breakdown available."

    return {
        "what_happened": (
            f"{metric.capitalize()} {direction_word} by {abs(pct):.1f}% versus its expected "
            f"baseline of {evidence['expected_value_baseline']:.2f} on {evidence['date']}, "
            f"a {good_bad} movement classified as {evidence['severity']} severity."
        ),
        "observed_drivers": f"Statistically correlated movement observed in: {drivers_text}",
        "significance": (
            f"Deviation of {pct:+.1f}% with a z-score of {evidence['z_score']} exceeds the "
            f"configured anomaly thresholds, indicating this is unlikely to be normal variation."
        ),
        "investigate_next": (
            "Review the listed drivers for pricing, inventory, marketing, or operational changes "
            "on the affected date, and confirm whether the movement is isolated or part of a "
            "sustained trend."
        ),
    }
