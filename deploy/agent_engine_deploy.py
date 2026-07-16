"""Deploy the VIGIL orchestrator + signal agent to Vertex AI Agent Engine.

This completes the skeleton in deploy/adk_app.py: it wraps the two pure-Python
entrypoints (process_case, detect_signal) as ADK FunctionTools on an ADK Agent
and pushes that agent to Agent Engine (Reasoning Engine), which gives it a
managed, identity-bound runtime that Gemini Enterprise can register.

    python -m deploy.agent_engine_deploy

Environment (deploy/deploy.sh sets these from terraform outputs):
    VIGIL_PROJECT         GCP project id
    VIGIL_LOCATION        region, e.g. us-central1
    VIGIL_STAGING_BUCKET  GCS staging bucket (no gs:// prefix)
    VIGIL_AGENT_SA        runtime service account email (vigil-agent@...)
    VIGIL_DATASET, VIGIL_MODEL_PRO, VIGIL_MODEL_FLASH, ...  (passed to the runtime)

NOTE: the ADK / vertexai Agent Engine surface evolves quickly. The call shape
below targets `vertexai` >= 1.95 with `google-adk`. If your installed versions
differ, the one place to adjust is build_and_deploy(); the agent logic in
vigil/ is untouched and stays portable.
"""
from __future__ import annotations
import os
import sys

from deploy.adk_app import process_case, detect_signal


# Environment keys forwarded into the managed runtime so Settings.from_env()
# resolves the same configuration there as locally.
_FORWARDED_ENV = [
    "VIGIL_PROJECT", "VIGIL_LOCATION", "VIGIL_DATASET", "VIGIL_BUCKET",
    "VIGIL_MODEL_FLASH", "VIGIL_MODEL_PRO", "VIGIL_EMBED_MODEL",
    "VIGIL_SCOPE_VAX_TYPE", "VIGIL_SCOPE_MANUFACTURER",
    "VIGIL_MIN_NARRATIVE_CHARS", "VIGIL_LIVE_SLICE_SIZE", "VIGIL_HITL_THRESHOLD",
]


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"ERROR: {name} must be set (run via deploy/deploy.sh --agent)")
    return val


def build_and_deploy():
    import vertexai
    from vertexai import agent_engines
    from google.adk.agents import Agent
    from google.adk.tools import FunctionTool

    project = _require("VIGIL_PROJECT")
    location = os.environ.get("VIGIL_LOCATION", "us-central1")
    staging = _require("VIGIL_STAGING_BUCKET")
    service_account = _require("VIGIL_AGENT_SA")
    model_pro = os.environ.get("VIGIL_MODEL_PRO", "gemini-3-pro")

    vertexai.init(
        project=project,
        location=location,
        staging_bucket=f"gs://{staging}",
    )

    # The reasoning agent: routes a request to one of the two VIGIL tools.
    root_agent = Agent(
        name="vigil_orchestrator",
        model=model_pro,
        instruction=(
            "You are Project VIGIL, an agentic pharmacovigilance assistant on VAERS. "
            "Use process_case to run the full case pipeline (triage -> extraction -> "
            "grounded MedDRA coding -> seriousness + WHO-UMC causality -> narrative + QC) "
            "for a single report. Use detect_signal to answer aggregate safety-signal "
            "questions (PRR/ROR disproportionality) via guarded read-only SQL. "
            "Always surface confidence and HITL flags; never overstate causation."
        ),
        tools=[FunctionTool(process_case), FunctionTool(detect_signal)],
    )

    env_vars = {k: os.environ[k] for k in _FORWARDED_ENV if os.environ.get(k)}

    print(f"Deploying vigil_orchestrator to Agent Engine in {project}/{location} ...")
    remote_agent = agent_engines.create(
        agent_engine=root_agent,
        display_name="Project VIGIL - orchestrator + signal",
        description="Agentic pharmacovigilance: case processing + disproportionality signal detection.",
        requirements=[
            "google-adk",
            "google-cloud-aiplatform[agent_engines]",
            "google-genai>=1.0",
            "google-cloud-bigquery>=3.25",
            "google-cloud-storage>=2.18",
            "pydantic>=2.6",
            "sqlglot>=25",
            "numpy",
        ],
        extra_packages=["vigil", "deploy"],
        service_account=service_account,
        env_vars=env_vars,
    )

    print("Deployed.")
    print(f"  resource name: {remote_agent.resource_name}")
    print("Register this agent in Gemini Enterprise (see deploy/GEMINI-ENTERPRISE.md).")
    return remote_agent


if __name__ == "__main__":
    build_and_deploy()
