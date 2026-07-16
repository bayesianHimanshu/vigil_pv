# Surfacing VIGIL in Gemini Enterprise (no custom UI)

The UI is **configuration** in Gemini Enterprise (formerly Agentspace), not React code. Two things get wired:

1. **The agents** - the orchestrator (case processing) and the signal agent -
   are deployed to **Agent Engine / Agent Runtime** via a thin ADK adapter
   (`deploy/adk_app.py`) and registered in Gemini Enterprise.
2. **The data** - the curated BigQuery views become the reviewer-facing surfaces.

## What reviewers see (all inside Gemini Enterprise, zero front-end code)

| Surface | Backed by | What it does |
|---|---|---|
| Review queue | `vw_review_queue` | Cases the pipeline flagged for a human (low confidence / uncoded / QC) |
| Case detail | `vw_case_full` | Raw narrative + agent output + ground-truth + eval, side by side |
| Signal dashboard | the **signal agent** over `vw_signal_metrics` | Ask "any signal for X?" in natural language; get PRR/ROR + a cautious summary |
| Quality scorecard | `vw_eval_dashboard` | Coding F1 + seriousness accuracy vs human coders, by pipeline version |

## Wiring steps (one-time)

1. **Deploy the agents.** Package the orchestrator + signal agent with the ADK
   adapter and deploy to Agent Engine (see `deploy/adk_app.py`). This gives each
   agent a managed, identity-bound runtime.
2. **Register in Gemini Enterprise.** Add the deployed agents as available
   assistants/tools in your Gemini Enterprise app.
3. **Connect the data.** Point Gemini Enterprise data sources at the curated
   views (`vw_review_queue`, `vw_case_full`, `vw_eval_dashboard`) so reviewers
   can browse and search them without leaving the portal.
4. **Governance.** Bind agent identities (Agent Identity / Registry / Gateway),
   enforce VPC Service Controls + CMEK on the project, and rely on Cloud Audit
   Logs + the append-only BigQuery tables for the full trail.
