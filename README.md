# Business Anomaly Monitoring Agent

An end-to-end AI-powered agent that ingests business Excel data, statistically
detects unusual KPI movements, identifies the strongest contributing dimensions,
generates an evidence-only AI business summary, and triggers email alerts —
with a Streamlit UI for the whole workflow.

Built as a portfolio project for Data Analyst / Business Analyst / Product
Analyst / AI Automation interview conversations. Every design decision below is
something you should be able to explain and defend.

---

## Application Preview

The application provides an interactive Streamlit dashboard for anomaly
detection, driver analysis, AI-generated business summaries, email alerts,
and alert history.

Screenshots will be added after the final validation and testing of the
application.


## Why this architecture

The core principle: **statistics decides, the LLM explains.**

```
Excel file
   │
   ▼
loader.py
   │  Reads and normalizes Excel data
   ▼
validator.py
   │  Validates structure, types, required columns
   ▼
anomaly.py
   │  Rolling baseline → % change → z-score → severity
   │  Statistics decides whether an anomaly exists
   ▼
drivers.py
   │  Compares dimensions and related metrics
   │  Identifies what moved together with the anomaly
   ▼
llm.py
   │  Receives structured evidence only
   │  Generates an evidence-constrained business summary
   ▼
email_alert.py
   │  Checks severity → checks deduplication → sends email
   ▼
alert_history.py
   │  SQLite audit trail
   │  Dedup key: metric + date + direction
   ▼
app.py
      Streamlit UI connecting the workflow
```

Why split it this way? Each module has one job and one owner-of-truth:
- If detection logic is wrong, you only ever look in `anomaly.py`.
- If the AI "hallucinates" a cause, you can prove it didn't have access to raw
  data — only the JSON evidence object built in `llm.py::build_evidence_payload`.
- If duplicate emails go out, the bug is in `alert_history.py`'s dedup key, not
  scattered through the UI code.

---

## Anomaly detection method

For a given metric and date:

1. **Rolling baseline** — mean and standard deviation of the metric over the
   `rolling_window` periods *strictly before* the current date (default 7).
2. **Percentage change** — `(current - baseline_mean) / baseline_mean * 100`
3. **Z-score** — `(current - baseline_mean) / baseline_std`
4. **Flagging rule** — a point is only flagged as an anomaly if it clears
   **both** the percentage-change threshold *and* the z-score threshold.
   - Percentage-change alone would flag naturally volatile series constantly.
   - Z-score alone would flag tiny, business-irrelevant blips on very stable series.
   - Requiring both keeps flags meaningful in both statistical and business terms.
5. **Severity** — assigned from configurable magnitude bands on `|pct_change|`:
   `LOW ≥ 20%`, `MEDIUM ≥ 30%`, `HIGH ≥ 50%` (all adjustable in `config.py` or the UI).
6. **Direction vs. good/bad** — a raw UP/DOWN movement is translated into
   GOOD/BAD using `METRIC_DIRECTION` in `config.py`, since a revenue drop is bad
   but a returns drop is good — the statistics are symmetric either way, only the
   business-facing label changes.

All thresholds are configurable in `config.py` and live-adjustable from the
Streamlit sidebar — nothing is hard-coded into the detection logic itself.

## Driver analysis method

Once the **total** series for a metric is confirmed anomalous on a date,
`drivers.py` re-runs the same baseline-comparison math on each dimension slice
(e.g. each region individually) and on mechanically related metrics (orders,
profit, average order value) for that same date, then ranks slices by the
magnitude of their movement. This tells you *what moved together with* the
anomaly — it does not claim what *caused* it. That distinction is preserved
all the way into the AI summary (see below).

## LLM summary constraints

`llm.py` sends the model **only** the structured evidence object — actual
value, baseline, deviation %, z-score, severity, and the ranked driver
breakdown. It never sees raw rows and is explicitly instructed to:
- Treat "is this an anomaly" as already decided — it cannot second-guess it.
- Report **observed drivers** as measured facts (with numbers).
- Report **possible causes** as clearly labeled hypotheses, kept generic
  ("check for a pricing or promotion change in the affected region") rather
  than inventing a specific unverified event.

If `OPENAI_API_KEY` isn't set, `llm.py` falls back to a deterministic,
template-based summary built from the same evidence object, so the rest of the
app is fully demoable without any API key.

## Alerting & deduplication

- Emails are only sent for severities in `ALERT_SEVERITIES` (default:
  `MEDIUM`, `HIGH`) — configured in `config.py`.
- Before sending, `alert_history.py` checks for an existing alert with the same
  `(metric, date, direction)`. If one exists, the alert is skipped rather than
  resent.
- LOW-severity anomalies are not emailed because they are below the configured
  alerting threshold.
- Every alert attempt is recorded in `alert_history.db`, creating an audit
  trail of sent, skipped, and failed alerts.
- Including direction in the deduplication key allows an UP and DOWN anomaly on
  the same metric and date to be treated as separate alert events.

---

## Project structure

```
anomaly-agent/
├── app.py                     # Streamlit UI
├── config.py                  # All thresholds, paths, and env-based secrets
├── generate_sample_data.py    # Creates data/sample_sales_data.xlsx
├── requirements.txt
├── .env.example                # Copy to .env and fill in real values
├── data/
│   └── sample_sales_data.xlsx  # 90 days, 2 regions x 2 categories x products, with injected anomalies
└── src/
    ├── loader.py               # Excel → normalized DataFrame
    ├── validator.py            # Structural + row-level validation
    ├── anomaly.py              # Rolling baseline / % change / z-score / severity
    ├── drivers.py              # Dimension + related-metric driver analysis
    ├── llm.py                  # Evidence-constrained AI summary generation
    ├── email_alert.py          # SMTP alerts, severity-gated
    └── alert_history.py        # SQLite dedup + audit trail
```

## Excel input format

| Column | Required | Type | Notes |
|---|---|---|---|
| `date` | Yes | date | One row per date (+ optional dimension combo) |
| `revenue`, `orders`, `profit`, `customers`, `returns`, `cancellations` | At least one | numeric | Any subset is fine |
| `region`, `category`, `product`, `customer_segment` | No | text | Enables driver analysis if present |

Column headers are case/spacing-insensitive (`"Customer Segment"` and
`customer_segment` both work).

---

## Setup

```bash
# 1. Clone/copy the project, then create a virtual environment
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure secrets (optional — app works without these, using fallbacks)
cp .env.example .env
# edit .env with your OpenAI key and/or SMTP credentials

# 4. Generate the sample dataset (optional — one is already included)
python generate_sample_data.py

# 5. Run the app
streamlit run app.py
```

Then open the local URL Streamlit prints (usually `http://localhost:8501`),
upload `data/sample_sales_data.xlsx` (or your own file), pick a metric, and
explore.

### Running without any API keys

- No `OPENAI_API_KEY` → AI summaries fall back to a deterministic
  template built from the same evidence, so the app is still fully usable.
- No SMTP credentials → the app will attempt to send and report a clear
  "SMTP credentials are not configured" message instead of crashing; anomaly
  detection, driver analysis, and the audit trail all still work.

---

## Known limitations / future enhancements

This is intentionally a clean, explainable v1. Logical next steps:

- **Seasonality & weekday baselines** — currently the baseline is a flat
  rolling mean; a Tuesday isn't compared only to recent Tuesdays. Adding a
  day-of-week or seasonal decomposition baseline (e.g. STL) would reduce false
  positives on data with strong weekly patterns.
- **Sustained-trend detection** — right now each date is evaluated
  independently. A metric drifting steadily downward over 2 weeks without any
  single day crossing the threshold would currently be missed; a
  cumulative-drift or CUSUM-style check would catch this.
- **More advanced anomaly algorithms** — e.g. seasonal-hybrid ESD, isolation
  forest, or Prophet-based anomaly detection for noisier, multi-seasonal data.
- **Multi-metric correlated anomaly detection** — currently drivers are
  computed per-metric on demand; a future version could proactively flag when
  multiple metrics move anomalously together.
- **Enterprise email** — SMTP is the v1 transport; Microsoft Graph API (or
  SendGrid/SES) would be a natural swap for enterprise deployments, without
  changing anything upstream of `email_alert.py`.
- **Alert digesting** — batch multiple same-day anomalies across metrics into
  a single digest email instead of one email per metric.

## Testing & Validation

The application was tested across anomaly severity levels and alert scenarios
to verify that detection and email behavior work as intended.

### Alert behavior tested

| Scenario | Expected behavior | Result |
|---|---|---|
| MEDIUM anomaly on first alert | Email is sent | ✅ Passed |
| HIGH anomaly | HIGH severity detected | ✅ Passed |
| Same metric + date + direction triggered again | Duplicate alert is skipped | ✅ Passed |
| LOW-severity anomaly | Email is not sent | ✅ Passed |
| Alert history checked after processing | Alert is recorded in SQLite | ✅ Passed |

**Note:** The application has now been validated with LOW, MEDIUM, and HIGH severity anomalies. HIGH-severity detection, driver analysis, and AI summary generation were successfully verified. Alert deduplication was also confirmed for the HIGH-severity test because the same metric, date, and direction had already been recorded.

### Example test result

For the tested revenue anomaly on `2026-07-10`:

- Baseline: `101,565.30`
- Revenue movement: `-35.5%`
- Z-score: `-4.36`
- Severity: `MEDIUM`
- Direction: `DOWN`
- First alert attempt: Email sent successfully
- Repeated alert attempt: Duplicate alert skipped

This confirms that the system can detect a statistically significant business
movement, classify its severity, send an eligible alert, and prevent repeated
notifications for the same metric, date, and direction.

## Interview talking points

- Why detection and explanation are deliberately separated (auditability,
  prevents LLM hallucination from ever changing a business decision).
- Why both a percentage-change AND a z-score threshold are required (trade-off
  between magnitude-based and volatility-based false positives).
- How the dedup key (`metric`, `date`, `direction`) in SQLite prevents alert
  fatigue while allowing opposite-direction events to be treated separately.
- How the driver analysis distinguishes **correlation** (what the data shows
  moved together) from **causation** (a hypothesis the LLM is only allowed to
  suggest, explicitly labeled as such).

