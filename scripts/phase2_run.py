"""Phase 2 - run extraction + grounded coding over the slice and score MedDRA F1.

    python -m scripts.phase2_run --n 200

Builds the embedding grounder over the in-scope PT list, runs the two-agent
pipeline (append-only), then prints the coding concordance vs human coders
from vw_eval_dashboard, plus the worst-coded cases for error review.
"""
from __future__ import annotations
import argparse
from vigil.config import Settings, PIPELINE_VERSION_PHASE2
from vigil.clients import BigQuery, genai_client
from vigil.llm import StructuredLLM
from vigil.extraction_agent import ExtractionAgent
from vigil.coding_agent import CodingAgent
from vigil.grounding import build_embedding_grounder
from vigil.pipeline import run_case
from vigil.evaluation import coding_scorecard_sql, coding_worst_cases_sql


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None)
    args = ap.parse_args()

    cfg = Settings.from_env()
    n = args.n or cfg.live_slice_size
    bq = BigQuery(cfg)
    client = genai_client(cfg)

    extractor = ExtractionAgent(StructuredLLM(client, cfg.model_flash))
    print(f"Building grounder over the in-scope PT list ({cfg.embed_model}) ...")
    coder = CodingAgent(StructuredLLM(client, cfg.model_flash), build_embedding_grounder(cfg))

    cases = bq.query(
        f"SELECT vaers_id, symptom_text, recvdate FROM `{cfg.ds}.vw_demo_slice` LIMIT @n",
        {"n": n})
    print(f"Processing {len(cases)} cases (extraction + coding) ...")

    ok = hitl = 0
    for i, row in enumerate(cases, 1):
        try:
            res = run_case(cfg, row["vaers_id"], row["symptom_text"], row["recvdate"],
                           extractor=extractor, coder=coder, bq=bq,
                           pipeline_version=PIPELINE_VERSION_PHASE2)
            ok += 1
            hitl += int(res["hitl_required"])
            if i % 25 == 0:
                print(f"  {i}/{len(cases)} done")
        except Exception as e:
            print(f"  case {row['vaers_id']} failed: {str(e).splitlines()[0][:100]}")

    print(f"\nProcessed {ok} cases · {hitl} flagged for review")

    params = {"pv": PIPELINE_VERSION_PHASE2}
    score = bq.query_one(coding_scorecard_sql(cfg), params)
    print("\n=== MedDRA coding concordance vs human coders ===")
    if score:
        for k, v in score.items():
            print(f"  {k:16s}: {v}")
    print("\nLowest-F1 cases (error review):")
    for r in bq.query(coding_worst_cases_sql(cfg), params):
        print(f"  {r['vaers_id']}  f1={r['f1']}  tp={r['tp']} fp={r['fp']} fn={r['fn']}")


if __name__ == "__main__":
    main()
