"""Narrative + QC agent.

Drafts a concise ICSR case narrative from the assembled structured case and
runs a completeness/consistency QC pass, recommending human review when
issues are found. Gemini Pro (reasoning + writing).
"""

from __future__ import annotations
import json
from typing import Optional, Tuple

from .contracts import (
    NarrativeQCOutput,
    ExtractedCase,
    CodingResult,
    SeriousnessAssessment,
    CausalityAssessment,
)
from .config import NARRATIVE_AGENT_VERSION, NARRATIVE_PROMPT_VERSION
from .llm import StructuredLLM, LLMMeta

SYSTEM_PROMPT = """You are a pharmacovigilance case-narrative writer and QC reviewer.
Write a concise, factual ICSR case narrative in past tense from the structured case:
patient, suspect/concomitant products, events (use the coded MedDRA terms), timing,
seriousness, and causality. Include only information present in the case.

Then QC the case: rate completeness in [0,1], list any gaps, and raise QC flags
(missing_field, inconsistency, temporal_anomaly, low_confidence_coding, unmapped_event)
with severity info/warning/error. Recommend human review (hitl_recommended = true) if
there are error-level flags, material gaps, or low overall confidence.
Report a calibrated overall confidence in [0,1].
"""


def _assembled(
    extracted: ExtractedCase,
    coded: Optional[CodingResult],
    seriousness: Optional[SeriousnessAssessment],
    causality: Optional[CausalityAssessment],
) -> str:
    parts = {
        "extracted": extracted.model_dump(mode="json"),
        "coded": coded.model_dump(mode="json") if coded else None,
        "seriousness": seriousness.model_dump(mode="json") if seriousness else None,
        "causality": causality.model_dump(mode="json") if causality else None,
    }
    return json.dumps(parts, indent=2)


class NarrativeQCAgent:
    name = "narrative_qc"
    version = NARRATIVE_AGENT_VERSION
    prompt_version = NARRATIVE_PROMPT_VERSION

    def __init__(self, llm: StructuredLLM):
        self._llm = llm

    def run(
        self,
        vaers_id: str,
        *,
        extracted: ExtractedCase,
        coded: Optional[CodingResult] = None,
        seriousness: Optional[SeriousnessAssessment] = None,
        causality: Optional[CausalityAssessment] = None,
    ) -> Tuple[NarrativeQCOutput, LLMMeta]:
        out, meta = self._llm.generate(
            system=SYSTEM_PROMPT,
            user=f"Assembled case (id {vaers_id}):\n\n"
            f"{_assembled(extracted, coded, seriousness, causality)}",
            schema=NarrativeQCOutput,
            temperature=0.2,
        )
        return out, meta  # type: ignore[return-value]
