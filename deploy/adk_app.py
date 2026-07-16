"""ADK deployment adapter (skeleton) - the ONLY framework-aware code.

The pipeline core (orchestrator + agents) is plain Python. To surface it in
Gemini Enterprise it must run on Agent Engine, which speaks ADK. This adapter
wraps the existing logic as ADK tools so nothing in `vigil/` depends on a
framework - the portability boundary the architecture promised.

This is scaffolding: confirm the imports/calls against your installed ADK and
Agent Engine versions (the ADK surface evolves). The *pattern* is the point:
expose `orchestrator.run_case` and `signal_agent.answer` as tools on an ADK
agent, then deploy that agent to Agent Engine.
"""
from __future__ import annotations

# from google.adk.agents import Agent
# from google.adk.tools import FunctionTool
# from vertexai import agent_engines

from vigil.config import Settings
from vigil.clients import BigQuery, genai_client
from vigil.llm import StructuredLLM
from vigil.triage_agent import TriageAgent
from vigil.extraction_agent import ExtractionAgent
from vigil.coding_agent import CodingAgent
from vigil.assessment_agent import AssessmentAgent
from vigil.narrative_qc_agent import NarrativeQCAgent
from vigil.signal_agent import SignalAgent
from vigil.grounding import build_embedding_grounder
from vigil.orchestrator import Orchestrator


def build_core(cfg: Settings):
    """Construct the pure-Python orchestrator + signal agent (framework-free)."""
    bq = BigQuery(cfg)
    client = genai_client(cfg)
    flash = lambda: StructuredLLM(client, cfg.model_flash)
    pro = lambda: StructuredLLM(client, cfg.model_pro)

    orch = Orchestrator(
        cfg, bq,
        triage=TriageAgent(flash()),
        extractor=ExtractionAgent(flash()),
        coder=CodingAgent(flash(), build_embedding_grounder(cfg)),
        assessor=AssessmentAgent(pro()),
        narrator=NarrativeQCAgent(pro()),
    )
    view_fqn = f"{cfg.ds}.vw_signal_metrics"
    signal = SignalAgent(pro(), lambda sql: [dict(r) for r in bq.query(sql)], view_fqn)
    return orch, signal


# --- ADK tool wrappers (thin) -------------------------------------------------

def process_case(vaers_id: str, narrative: str) -> dict:
    """Tool: run the full case pipeline for one report."""
    cfg = Settings.from_env()
    orch, _ = build_core(cfg)
    return orch.run_case(vaers_id, narrative, received_date=None)


def detect_signal(question: str) -> dict:
    """Tool: answer an aggregate safety-signal question."""
    cfg = Settings.from_env()
    _, signal = build_core(cfg)
    out, _meta = signal.answer(question)
    return out.model_dump(mode="json")


# --- Agent definition + deploy (confirm against your ADK / Agent Engine) ------

def build_adk_agent():
    raise NotImplementedError(
        "Wrap process_case / detect_signal as ADK FunctionTools on an ADK Agent, "
        "e.g. Agent(model=..., tools=[FunctionTool(process_case), FunctionTool(detect_signal)]). "
        "Then deploy with vertexai.agent_engines.create(agent, requirements=[...]) and register "
        "the deployed agent in Gemini Enterprise. See deploy/GEMINI-ENTERPRISE.md."
    )


if __name__ == "__main__":
    print("ADK adapter skeleton - see build_adk_agent() and deploy/GEMINI-ENTERPRISE.md")
