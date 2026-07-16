"""Coding agent (Phase 2).

For each verbatim event: retrieve candidate MedDRA PTs (grounding), then ask
Gemini to assign the single best PT, preferring the grounded candidates.
Plain Python over the thin LLM + Grounder interfaces.
"""
from __future__ import annotations
from typing import List, Tuple

from .contracts import CodingOutput
from .config import CODING_AGENT_VERSION, CODING_PROMPT_VERSION
from .llm import StructuredLLM, LLMMeta
from .grounding import Grounder

SYSTEM_PROMPT = """You are a MedDRA coding specialist for pharmacovigilance.
For each adverse-event term, assign the single best MedDRA Preferred Term (PT).

Rules:
- Prefer a PT from the provided candidate list when one is clinically appropriate.
- If a candidate is a close-but-imperfect match, use it and set requires_review = true.
- If no candidate fits and you are not confident in a PT, put the verbatim in 'uncoded'.
- Do not invent terms. Report a calibrated confidence in [0,1] for each coding and overall.
"""


def _render(events: List[str], candidates) -> str:
    lines = []
    for i, v in enumerate(events, 1):
        cands = candidates.get(v) or []
        shown = "; ".join(cands) if cands else "(no candidates retrieved)"
        lines.append(f"{i}. Event: {v}\n   Candidate PTs: {shown}")
    return "Code each event below.\n\n" + "\n".join(lines)


class CodingAgent:
    name = "coding"
    version = CODING_AGENT_VERSION
    prompt_version = CODING_PROMPT_VERSION

    def __init__(self, llm: StructuredLLM, grounder: Grounder):
        self._llm = llm
        self._grounder = grounder

    def code(self, vaers_id: str, events: List[str]) -> Tuple[CodingOutput, LLMMeta]:
        if not events:
            return CodingOutput.model_validate({"result": {"coded": [], "uncoded": []}, "confidence": 1.0}), \
                LLMMeta(model=self._llm.model, input_tokens=0, output_tokens=0, latency_ms=0)
        candidates = self._grounder.ground(events)
        result, meta = self._llm.generate(
            system=SYSTEM_PROMPT,
            user=_render(events, candidates),
            schema=CodingOutput,
            temperature=0.0,
        )
        return result, meta  # type: ignore[return-value]
