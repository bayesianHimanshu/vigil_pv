"""Triage agent (Phase 3 - first step of the full pipeline).

Screens a report for the four minimum ICSR validity criteria and does an
initial seriousness/priority screen. Gemini Flash (fast, high-volume).
"""
from __future__ import annotations
from typing import Optional, Tuple

from .contracts import TriageOutput
from .config import TRIAGE_AGENT_VERSION, TRIAGE_PROMPT_VERSION
from .llm import StructuredLLM, LLMMeta

SYSTEM_PROMPT = """You are a pharmacovigilance intake triage specialist.
Assess the report for the four minimum ICSR validity criteria:
an identifiable patient, an identifiable reporter, a suspect product, and an adverse event.
List any that are missing. Then screen seriousness: mark which seriousness criteria
appear (death, life_threatening, hospitalization, disability, congenital_anomaly,
other_medically_important) and assign a priority:
- expedited  : a serious case
- standard   : valid, non-serious
- non_serious: valid, clearly non-serious / minor
Report a calibrated confidence in [0,1]. Do not infer facts not present in the text.
"""


class TriageAgent:
    name = "triage"
    version = TRIAGE_AGENT_VERSION
    prompt_version = TRIAGE_PROMPT_VERSION

    def __init__(self, llm: StructuredLLM):
        self._llm = llm

    def triage(self, vaers_id: str, narrative: str,
               received_date: Optional[str] = None) -> Tuple[TriageOutput, LLMMeta]:
        out, meta = self._llm.generate(
            system=SYSTEM_PROMPT,
            user=f"Adverse-event report (id {vaers_id}):\n\n{narrative}",
            schema=TriageOutput,
            temperature=0.0,
        )
        return out, meta  # type: ignore[return-value]
