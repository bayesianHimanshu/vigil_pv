"""Phase 4 - run the signal agent against vw_signal_metrics.

    python -m scripts.phase4_run --question "Strongest signals for the in-scope product?"

Generates a guarded read-only SELECT, executes it, and prints the
disproportionality results plus a cautious natural-language summary.
"""
from __future__ import annotations
import argparse
from vigil.config import Settings
from vigil.clients import BigQuery, genai_client
from vigil.llm import StructuredLLM
from vigil.signal_agent import SignalAgent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", default="Which adverse events show the strongest disproportionality signal?")
    args = ap.parse_args()

    cfg = Settings.from_env()
    bq = BigQuery(cfg)
    view_fqn = f"{cfg.ds}.vw_signal_metrics"

    def run_sql(sql):
        return [dict(r) for r in bq.query(sql)]

    agent = SignalAgent(StructuredLLM(genai_client(cfg), cfg.model_pro), run_sql, view_fqn)
    out, _meta = agent.answer(args.question)

    print("=== Generated SQL (validated read-only) ===")
    print(out.generated_sql)
    print(f"\n=== Top signals ({len(out.results)} rows) ===")
    print(f"{'event_pt':40s} {'a':>5} {'prr':>8} {'ror':>8}  flag")
    for r in out.results[:25]:
        print(f"{r.event_pt[:40]:40s} {r.a:>5} {str(r.prr):>8} {str(r.ror):>8}  {r.signal_flag}")
    print("\n=== Summary ===")
    print(out.summary)
    if out.caveats:
        print("\nCaveats:")
        for c in out.caveats:
            print(f"  - {c}")


if __name__ == "__main__":
    main()
