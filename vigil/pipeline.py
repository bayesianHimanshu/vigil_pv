"""Single-case pipeline.

Runs extraction and (when a coder is supplied) coding for one case, writing
the APPEND-ONLY records: one agt_step_event per agent (the immutable log),
agt_case_output (the assembled case), and agt_run (run metadata, inserted
once at completion). Nothing is ever updated; re-processing yields a new
run_id.

`extractor`, `coder`, and `bq` are injected (duck-typed) so this module
imports no cloud libraries and is fully unit-testable with fakes.
"""

from __future__ import annotations
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Protocol, Tuple, List

from .config import Settings, PIPELINE_VERSION
from .contracts import ExtractionResult, CodingOutput
from .llm import LLMMeta


class ExtractorLike(Protocol):
    name: str
    version: str
    prompt_version: str

    def extract(
        self, vaers_id: str, narrative: str
    ) -> Tuple[ExtractionResult, LLMMeta]: ...


class CoderLike(Protocol):
    name: str
    version: str
    prompt_version: str

    def code(
        self, vaers_id: str, events: List[str]
    ) -> Tuple[CodingOutput, LLMMeta]: ...


class BQLike(Protocol):
    def insert_row(self, table: str, row: dict) -> None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _step_row(
    run_id: str,
    vaers_id: str,
    seq: int,
    agent,
    model: str,
    output: dict,
    confidence: float,
    meta: LLMMeta,
    input_text: str,
) -> dict:
    return {
        "event_id": uuid.uuid4().hex,
        "run_id": run_id,
        "vaers_id": vaers_id,
        "seq": seq,
        "agent_name": agent.name,
        "agent_version": agent.version,
        "model": model,
        "prompt_version": agent.prompt_version,
        "input_hash": hashlib.sha256(input_text.encode("utf-8")).hexdigest(),
        "output": json.dumps(output),  # JSON column
        "confidence": confidence,
        "input_tokens": meta.input_tokens,
        "output_tokens": meta.output_tokens,
        "latency_ms": meta.latency_ms,
        "created_at": _now(),
    }


def run_case(
    cfg: Settings,
    vaers_id: str,
    narrative: str,
    received_date: Optional[str],
    *,
    extractor: ExtractorLike,
    bq: BQLike,
    coder: Optional[CoderLike] = None,
    pipeline_version: str = PIPELINE_VERSION,
) -> dict:
    run_id = uuid.uuid4().hex
    started_at = _now()
    model_config: dict = {}

    # --- step 1: extraction ---
    extr, extr_meta = extractor.extract(vaers_id, narrative)
    model_config["extraction_model"] = extr_meta.model
    bq.insert_row(
        "agt_step_event",
        _step_row(
            run_id,
            vaers_id,
            1,
            extractor,
            extr_meta.model,
            extr.model_dump(mode="json"),
            extr.confidence,
            extr_meta,
            narrative,
        ),
    )

    # --- step 2: coding (Phase 2) ---
    coded_pts: List[str] = []
    coded_detail_json: Optional[str] = None
    cod_conf: Optional[float] = None
    n_uncoded = 0
    output_model = extr_meta.model
    if coder is not None:
        verbatims = [e.verbatim for e in extr.case.events]
        cod, cod_meta = coder.code(vaers_id, verbatims)
        model_config["coding_model"] = cod_meta.model
        output_model = cod_meta.model
        bq.insert_row(
            "agt_step_event",
            _step_row(
                run_id,
                vaers_id,
                2,
                coder,
                cod_meta.model,
                cod.model_dump(mode="json"),
                cod.confidence,
                cod_meta,
                " | ".join(verbatims),
            ),
        )
        coded_pts = [c.meddra_pt for c in cod.result.coded]
        coded_detail_json = json.dumps(cod.result.model_dump(mode="json"))
        cod_conf = cod.confidence
        n_uncoded = len(cod.result.uncoded)

    overall = extr.confidence if cod_conf is None else min(extr.confidence, cod_conf)
    hitl_required = overall < cfg.hitl_confidence_threshold or n_uncoded > 0

    # --- assembled case (append-only) ---
    bq.insert_row(
        "agt_case_output",
        {
            "run_id": run_id,
            "vaers_id": vaers_id,
            "pipeline_version": pipeline_version,
            "model": output_model,
            "extracted": json.dumps(extr.case.model_dump(mode="json")),  # JSON column
            "coded_pts": coded_pts,  # ARRAY<STRING>
            "coded_detail": coded_detail_json,  # JSON column or None
            "seriousness": None,  # Phase 3
            "causality": None,  # Phase 3
            "narrative": None,  # Phase 3
            "overall_confidence": overall,
            "hitl_required": hitl_required,
            "created_at": _now(),
        },
    )

    # --- run record (inserted once, at completion) ---
    bq.insert_row(
        "agt_run",
        {
            "run_id": run_id,
            "vaers_id": vaers_id,
            "pipeline_version": pipeline_version,
            "model_config": json.dumps(model_config),  # JSON column
            "status": "completed",
            "overall_confidence": overall,
            "hitl_required": hitl_required,
            "started_at": started_at,
            "finished_at": _now(),
        },
    )

    return {
        "run_id": run_id,
        "vaers_id": vaers_id,
        "confidence": overall,
        "hitl_required": hitl_required,
        "n_events": len(extr.case.events),
        "n_products": len(extr.case.products),
        "n_coded": len(coded_pts),
        "n_uncoded": n_uncoded,
    }
