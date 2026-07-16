"""GCP client factories + a thin BigQuery access layer.

Google libraries are imported here (not in pipeline.py) so the core
pipeline logic stays importable and unit-testable without cloud deps.
"""
from __future__ import annotations
import json
from typing import Any, Optional

from .config import Settings


def genai_client(cfg: Settings):
    from google import genai
    return genai.Client(vertexai=True, project=cfg.project, location=cfg.location)


def storage_client(cfg: Settings):
    from google.cloud import storage
    return storage.Client(project=cfg.project)


class BigQuery:
    """Minimal BigQuery wrapper exposing exactly what the pipeline needs."""

    def __init__(self, cfg: Settings):
        from google.cloud import bigquery
        self._bq = bigquery
        self.cfg = cfg
        self.client = bigquery.Client(project=cfg.project)

    def query(self, sql: str, params: Optional[dict] = None):
        job_config = None
        if params:
            qp = []
            for k, v in params.items():
                t = "INT64" if isinstance(v, int) and not isinstance(v, bool) else \
                    "FLOAT64" if isinstance(v, float) else "STRING"
                qp.append(self._bq.ScalarQueryParameter(k, t, v))
            job_config = self._bq.QueryJobConfig(query_parameters=qp)
        return list(self.client.query(sql, job_config=job_config).result())

    def query_one(self, sql: str, params: Optional[dict] = None) -> Optional[dict]:
        rows = self.query(sql, params)
        return dict(rows[0]) if rows else None

    def insert_row(self, table: str, row: dict[str, Any]) -> None:
        """Streaming insert of a single row (append-only).

        JSON-typed columns must be passed as JSON strings; callers in the
        pipeline already json.dumps() those fields.
        """
        table_id = self.cfg.table(table)
        errors = self.client.insert_rows_json(table_id, [row])
        if errors:
            raise RuntimeError(f"BigQuery insert into {table} failed: {errors}")
