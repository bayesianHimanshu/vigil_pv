"""Apply sql/data_model.sql to BigQuery, one statement at a time.

    python -m scripts.apply_ddl

Idempotency note: CREATE TABLE fails if the table exists. Use
`--recreate_views_only` to (re)apply just the CREATE [OR REPLACE] VIEWs,
or drop/recreate the dataset for a clean rebuild.
"""
from __future__ import annotations
import argparse
import os
import sqlglot
from google.cloud import bigquery
from vigil.config import Settings


def statements(sql_text: str):
    for stmt in sqlglot.parse(sql_text, dialect="bigquery"):
        if stmt is None:
            continue
        yield stmt.sql(dialect="bigquery")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", default=os.path.join(os.path.dirname(__file__), "..", "sql", "data_model.sql"))
    ap.add_argument("--views_only", action="store_true", help="apply only CREATE VIEW statements")
    args = ap.parse_args()

    cfg = Settings.from_env()
    client = bigquery.Client(project=cfg.project)
    # The DDL is written for dataset `pv_vigil`; rewrite if the configured name differs.
    text = open(args.sql).read().replace("pv_vigil.", f"{cfg.dataset}.")

    applied, skipped = 0, 0
    for sql in statements(text):
        if args.views_only and "CREATE VIEW" not in sql.upper() and "CREATE OR REPLACE VIEW" not in sql.upper():
            continue
        try:
            client.query(sql).result()
            applied += 1
            print("OK  ", sql.splitlines()[0][:80])
        except Exception as e:
            skipped += 1
            print("SKIP", sql.splitlines()[0][:80], "->", str(e).splitlines()[0][:80])
    print(f"\napplied={applied} skipped={skipped}")


if __name__ == "__main__":
    main()
