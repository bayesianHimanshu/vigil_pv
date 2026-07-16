"""Extraction agent

Plain Python: a system prompt + one structured call. No agent framework in
the core. For GCP deployment this is wrapped as an ADK tool/agent by a thin
adapter (not needed to run the pipeline locally or in a batch job).
"""
from __future__ import annotations
from typing import Tuple

from .contracts import ExtractionResult
from .config import EXTRACTION_AGENT_VERSION, EXTRACTION_PROMPT_VERSION
from .llm import StructuredLLM, LLMMeta

SYSTEM_PROMPT = """You are a pharmacovigilance case-intake specialist.
From the adverse-event report narrative, extract only what is explicitly stated:
- patient age (years) and sex
- products given, each marked as 'suspect' (the product under investigation) or 'concomitant'
- adverse events, each as the verbatim term used in the text
- vaccination date, symptom onset date, and days to onset, as ISO 8601 dates when stated
- concomitant medications, relevant medical history, and known allergies

Rules:
- Do NOT infer, normalize, or code terms; capture events verbatim.
- Use null for any field not stated in the narrative. Do not guess.
- Report a calibrated confidence in [0,1] for the overall extraction.
"""


class ExtractionAgent:
    name = "extraction"
    version = EXTRACTION_AGENT_VERSION
    prompt_version = EXTRACTION_PROMPT_VERSION

    def __init__(self, llm: StructuredLLM):
        self._llm = llm

    def extract(self, vaers_id: str, narrative: str) -> Tuple[ExtractionResult, LLMMeta]:
        result, meta = self._llm.generate(
            system=SYSTEM_PROMPT,
            user=f"Adverse-event report (id {vaers_id}):\n\n{narrative}",
            schema=ExtractionResult,
            temperature=0.0,
        )
        return result, meta  # type: ignore[return-value]
