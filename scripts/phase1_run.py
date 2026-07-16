"""Phase 1 - run the extraction agent over the demo slice and score it.

    python -m scripts.phase1_run --n 200

Reads narrative-rich in-scope cases from vw_demo_slice, runs extraction,
writes append-only records, then builds vw_eval_extraction and prints the
concordance scorecard vs human ground truth.
"""
from __future__ import annotations
import argparse
from vigil.config import Settings
from vigil.clients import BigQuery, genai_client
from vigil.llm import StructuredLLM
from vigil.extraction_agent import ExtractionAgent
from vigil.pipeline import run_case
from vigil.evaluation import eval_view_sql, scorecard_sql


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None, help="number of cases (default: config live_slice_size)")
    args = ap.parse_args()

    cfg = Settings.from_env()
    n = args.n or cfg.live_slice_size
    bq = BigQuery(cfg)
    extractor = ExtractionAgent(StructuredLLM(genai_client(cfg), cfg.model_flash))

    cases = bq.query(
        f"SELECT vaers_id, symptom_text, recvdate FROM `{cfg.ds}.vw_demo_slice` LIMIT @n",
        {"n": n},
    )
    print(f"Processing {len(cases)} cases with {cfg.model_flash} ...")

    ok = hitl = 0
    for i, row in enumerate(cases, 1):
        try:
            res = run_case(cfg, row["vaers_id"], row["symptom_text"], row["recvdate"],
                           extractor=extractor, bq=bq)
            ok += 1
            hitl += int(res["hitl_required"])
            if i % 25 == 0:
                print(f"  {i}/{len(cases)} done")
        except Exception as e:
            print(f"  case {row['vaers_id']} failed: {str(e).splitlines()[0][:100]}")

    print(f"\nProcessed {ok} cases · {hitl} flagged for human review")

    print("Building eval view + scorecard ...")
    bq.query(eval_view_sql(cfg))
    score = bq.query_one(scorecard_sql(cfg))
    print("\n=== Extraction concordance vs human ground truth ===")
    for k, v in score.items():
        print(f"  {k:18s}: {v}")


if __name__ == "__main__":
    main()
