"""Orchestrator.

Coordinates the full case pipeline: triage -> extraction -> coding ->
assessment -> narrative+QC. Each present agent contributes one append-only
agt_step_event (seq 1..5); the assembled case lands in agt_case_output and
the run record in agt_run. Any agent may be omitted (the orchestrator runs
whatever it is given, in order), so earlier phases remain reproducible.

`bq` and the agents are injected (duck-typed) - no cloud imports here, so the
full chain is unit-testable with fakes.
"""

from __future__ import annotations
import json
import uuid
from typing import Optional, List

from .config import Settings, PIPELINE_VERSION_PHASE3
from .pipeline import _step_row, _now, BQLike


class Orchestrator:
    def __init__(
        self,
        cfg: Settings,
        bq: BQLike,
        *,
        extractor,
        triage=None,
        coder=None,
        assessor=None,
        narrator=None,
        pipeline_version: str = PIPELINE_VERSION_PHASE3,
    ):
        self.cfg = cfg
        self.bq = bq
        self.triage = triage
        self.extractor = extractor
        self.coder = coder
        self.assessor = assessor
        self.narrator = narrator
        self.pipeline_version = pipeline_version

    def run_case(
        self, vaers_id: str, narrative: str, received_date: Optional[str]
    ) -> dict:
        run_id = uuid.uuid4().hex
        started_at = _now()
        model_config: dict = {}
        confidences: List[float] = []
        seq = 0

        def emit(agent, model, output_dict, confidence, input_text, key):
            nonlocal seq
            seq += 1
            self.bq.insert_row(
                "agt_step_event",
                _step_row(
                    run_id,
                    vaers_id,
                    seq,
                    agent,
                    model,
                    output_dict,
                    confidence,
                    _meta,
                    input_text,
                ),
            )
            model_config[key] = model

        # 1) triage (optional)
        if self.triage is not None:
            t, _meta = self.triage.triage(vaers_id, narrative, received_date)
            emit(
                self.triage,
                _meta.model,
                t.model_dump(mode="json"),
                t.confidence,
                narrative,
                "triage_model",
            )
            confidences.append(t.confidence)

        # 2) extraction (required)
        extr, _meta = self.extractor.extract(vaers_id, narrative)
        emit(
            self.extractor,
            _meta.model,
            extr.model_dump(mode="json"),
            extr.confidence,
            narrative,
            "extraction_model",
        )
        confidences.append(extr.confidence)

        # 3) coding (optional)
        coded = None
        coded_pts: List[str] = []
        coded_detail_json: Optional[str] = None
        n_uncoded = 0
        if self.coder is not None:
            verbatims = [e.verbatim for e in extr.case.events]
            cod, _meta = self.coder.code(vaers_id, verbatims)
            emit(
                self.coder,
                _meta.model,
                cod.model_dump(mode="json"),
                cod.confidence,
                " | ".join(verbatims),
                "coding_model",
            )
            coded = cod.result
            coded_pts = [c.meddra_pt for c in cod.result.coded]
            coded_detail_json = json.dumps(cod.result.model_dump(mode="json"))
            n_uncoded = len(cod.result.uncoded)
            confidences.append(cod.confidence)

        # 4) assessment (optional)
        seriousness_json = None
        causality_json = None
        seriousness_obj = None
        causality_obj = None
        if self.assessor is not None:
            a, _meta = self.assessor.assess(vaers_id, extracted=extr.case, coded=coded)
            emit(
                self.assessor,
                _meta.model,
                a.model_dump(mode="json"),
                a.confidence,
                vaers_id,
                "assessment_model",
            )
            seriousness_obj, causality_obj = a.seriousness, a.causality
            seriousness_json = json.dumps(a.seriousness.model_dump(mode="json"))
            causality_json = json.dumps(a.causality.model_dump(mode="json"))
            confidences.append(a.confidence)

        # 5) narrative + QC (optional)
        narrative_text = None
        hitl_recommended = False
        if self.narrator is not None:
            nq, _meta = self.narrator.run(
                vaers_id,
                extracted=extr.case,
                coded=coded,
                seriousness=seriousness_obj,
                causality=causality_obj,
            )
            emit(
                self.narrator,
                _meta.model,
                nq.model_dump(mode="json"),
                nq.overall_confidence,
                vaers_id,
                "narrative_model",
            )
            narrative_text = nq.narrative
            hitl_recommended = nq.hitl_recommended
            confidences.append(nq.overall_confidence)

        overall = min(confidences) if confidences else 0.0
        hitl_required = (
            overall < self.cfg.hitl_confidence_threshold
            or n_uncoded > 0
            or hitl_recommended
        )

        self.bq.insert_row(
            "agt_case_output",
            {
                "run_id": run_id,
                "vaers_id": vaers_id,
                "pipeline_version": self.pipeline_version,
                "model": model_config.get("extraction_model"),
                "extracted": json.dumps(extr.case.model_dump(mode="json")),
                "coded_pts": coded_pts,
                "coded_detail": coded_detail_json,
                "seriousness": seriousness_json,
                "causality": causality_json,
                "narrative": narrative_text,
                "overall_confidence": overall,
                "hitl_required": hitl_required,
                "created_at": _now(),
            },
        )

        self.bq.insert_row(
            "agt_run",
            {
                "run_id": run_id,
                "vaers_id": vaers_id,
                "pipeline_version": self.pipeline_version,
                "model_config": json.dumps(model_config),
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
            "steps": seq,
            "confidence": overall,
            "hitl_required": hitl_required,
            "n_coded": len(coded_pts),
            "n_uncoded": n_uncoded,
            "serious": seriousness_obj.serious if seriousness_obj else None,
        }
