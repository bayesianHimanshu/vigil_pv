"""Phase 0 - load VAERS and build the foundation.

    python -m scripts.phase0_load \
        --data 2024VAERSDATA.csv --vax 2024VAERSVAX.csv --symptoms 2024VAERSSYMPTOMS.csv

Prereq: apply the DDL first (python -m scripts.apply_ddl).
"""
from __future__ import annotations
import argparse
from vigil.config import Settings
from vigil.loader import load_all, build_reference_and_slice


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="VAERSDATA csv")
    ap.add_argument("--vax", required=True, help="VAERSVAX csv")
    ap.add_argument("--symptoms", required=True, help="VAERSSYMPTOMS csv")
    args = ap.parse_args()

    cfg = Settings.from_env()
    print(f"Project {cfg.project} · dataset {cfg.dataset} · scope {cfg.scope_vax_type}")

    print("\nLoading raw tables ...")
    counts = load_all(cfg, args.data, args.vax, args.symptoms)
    for t in ("raw_vaers_data", "raw_vaers_vax", "raw_vaers_symptoms"):
        print(f"  {t:22s} {counts[t]:>8,} rows")

    print("\nDeriving reference + slice ...")
    summary = build_reference_and_slice(cfg)
    print(f"  in-scope products : {summary['in_scope_products']}")
    print(f"  MedDRA PTs        : {summary['meddra_pts']}")
    print(f"  demo slice cases  : {summary['demo_slice_cases']}")
    print("\nPhase 0 complete.")


if __name__ == "__main__":
    main()
