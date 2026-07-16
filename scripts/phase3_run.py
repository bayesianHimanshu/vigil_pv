"""Phase 3 - run the full case pipeline (all five agents) and score it.

    python -m scripts.phase3_run --n 200

Chains triage -> extraction -> coding -> assessment -> narrative+QC via the
orchestrator (append-only), then prints coding F1 + seriousness accuracy vs
human coders and the WHO-UMC causality distribution.
"""
from __future__ import annotations
import argparse
from vigil.config import Settings, PIPELINE_VERSION_PHASE3
from vigil.clients import BigQuery, genai_client
from vigil.llm import StructuredLLM
from vigil.triage_agent import TriageAgent
from vigil.extraction_agent import ExtractionAgent
from vigil.coding_agent import CodingAgent
from vigil.assessment_agent import AssessmentAgent
from vigil.narrative_qc_agent import NarrativeQCAgent
from vigil.grounding import build_embedding_grounder
from vigil.orchestrator import Orchestrator
from vigil.evaluation import phase3_scorecard_sql, causality_distribution_sql


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None)
    args = ap.parse_args()

    cfg = Settings.from_env()
    n = args.n or cfg.live_slice_size
    bq = BigQuery(cfg)
    client = genai_client(cfg)

    flash = lambda: StructuredLLM(client, cfg.model_flash)
    pro = lambda: StructuredLLM(client, cfg.model_pro)

    print(f"Building grounder over the in-scope PT list ({cfg.embed_model}) ...")
    orch = Orchestrator(
        cfg, bq,
        triage=TriageAgent(flash()),
        extractor=ExtractionAgent(flash()),
        coder=CodingAgent(flash(), build_embedding_grounder(cfg)),
        assessor=AssessmentAgent(pro()),
        narrator=NarrativeQCAgent(pro()),
        pipeline_version=PIPELINE_VERSION_PHASE3,
    )

    cases = bq.query(
        f"SELECT vaers_id, symptom_text, recvdate FROM `{cfg.ds}.vw_demo_slice` LIMIT @n",
        {"n": n})
    print(f"Processing {len(cases)} cases through the full pipeline ...")

    ok = hitl = serious = 0
    for i, row in enumerate(cases, 1):
        try:
            res = orch.run_case(row["vaers_id"], row["symptom_text"], row["recvdate"])
            ok += 1
            hitl += int(res["hitl_required"])
            serious += int(bool(res["serious"]))
            if i % 25 == 0:
                print(f"  {i}/{len(cases)} done")
        except Exception as e:
            print(f"  case {row['vaers_id']} failed: {str(e).splitlines()[0][:100]}")

    print(f"\nProcessed {ok} cases · {serious} assessed serious · {hitl} flagged for review")

    params = {"pv": PIPELINE_VERSION_PHASE3}
    score = bq.query_one(phase3_scorecard_sql(cfg), params)
    print("\n=== Concordance vs human coders ===")
    if score:
        for k, v in score.items():
            print(f"  {k:20s}: {v}")
    print("\nWHO-UMC causality distribution (shown, not scored):")
    for r in bq.query(causality_distribution_sql(cfg), params):
        print(f"  {r['category']:14s}: {r['n']}")


if __name__ == "__main__":
    main()
