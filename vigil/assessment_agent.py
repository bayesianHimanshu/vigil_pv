from __future__ import annotations
from typing import Optional, Tuple, List

from .contracts import AssessmentOutput, ExtractedCase, CodingResult
from .config import ASSESSMENT_AGENT_VERSION, ASSESSMENT_PROMPT_VERSION
from .llm import StructuredLLM, LLMMeta

SYSTEM_PROMPT = """You are a pharmacovigilance medical assessor.

Seriousness: determine whether the case is serious and list which ICH E2B
criteria are met: death, life_threatening, hospitalization, disability,
congenital_anomaly, other_medically_important.

Causality: assess the relationship between the suspect product and the events
using the WHO-UMC system. Choose exactly one category:
- certain, probable, possible, unlikely, conditional, unassessable
Consider temporal relationship, plausibility, dechallenge/rechallenge if stated,
and alternative explanations. Give a concise rationale grounded only in the case.
Report a calibrated confidence in [0,1]. Do not invent facts.
"""


def _summary(extracted: ExtractedCase, coded: Optional[CodingResult]) -> str:
    p = extracted.patient
    lines = [f"Patient: age {p.age_years}, sex {p.sex.value}"]
    if extracted.products:
        lines.append("Products: " + "; ".join(
            f"{pr.name} [{pr.role.value}]" for pr in extracted.products))
    if coded and coded.coded:
        lines.append("Coded events (MedDRA PT): " + "; ".join(c.meddra_pt for c in coded.coded))
    else:
        lines.append("Events: " + "; ".join(e.verbatim for e in extracted.events))
    lines.append(f"Vaccination date: {extracted.vaccination_date}; "
                 f"onset: {extracted.onset_date}; days to onset: {extracted.days_to_onset}")
    if extracted.medical_history:
        lines.append("History: " + "; ".join(extracted.medical_history))
    return "\n".join(lines)


class AssessmentAgent:
    name = "assessment"
    version = ASSESSMENT_AGENT_VERSION
    prompt_version = ASSESSMENT_PROMPT_VERSION

    def __init__(self, llm: StructuredLLM):
        self._llm = llm

    def assess(self, vaers_id: str, *, extracted: ExtractedCase,
               coded: Optional[CodingResult] = None) -> Tuple[AssessmentOutput, LLMMeta]:
        out, meta = self._llm.generate(
            system=SYSTEM_PROMPT,
            user=f"Assess this case (id {vaers_id}):\n\n{_summary(extracted, coded)}",
            schema=AssessmentOutput,
            temperature=0.0,
        )
        return out, meta  # type: ignore[return-value]
