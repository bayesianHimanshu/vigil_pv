"""
Loads the three VAERS CSVs into BigQuery raw tables (faithfully, handling
the Latin-1 encoding and blank fields), keeps a copy in Cloud Storage for
lineage, then derives ref_product_scope, ref_meddra_pt and the demo slice
view for the chosen single product family.

The raw tables, vw_symptoms_long and vw_gt_* views must already exist
(apply sql/data_model.sql first - see scripts/apply_ddl.py).
"""

from __future__ import annotations
import os
import uuid
from typing import List

from .config import Settings
from .clients import BigQuery, storage_client

# Expected columns per raw table (lowercase) and which are numeric.
DATA_COLS = [
    "vaers_id",
    "recvdate",
    "state",
    "age_yrs",
    "cage_yr",
    "cage_mo",
    "sex",
    "rpt_date",
    "symptom_text",
    "died",
    "datedied",
    "l_threat",
    "er_visit",
    "hospital",
    "hospdays",
    "x_stay",
    "disable",
    "recovd",
    "vax_date",
    "onset_date",
    "numdays",
    "lab_data",
    "v_adminby",
    "v_fundby",
    "other_meds",
    "cur_ill",
    "history",
    "prior_vax",
    "splttype",
    "form_vers",
    "todays_date",
    "birth_defect",
    "ofc_visit",
    "er_ed_visit",
    "allergies",
]
DATA_NUM = ["age_yrs", "cage_yr", "cage_mo", "hospdays", "numdays"]

VAX_COLS = [
    "vaers_id",
    "vax_type",
    "vax_manu",
    "vax_lot",
    "vax_dose_series",
    "vax_route",
    "vax_site",
    "vax_name",
]

SYM_COLS = [
    "vaers_id",
    "symptom1",
    "symptomversion1",
    "symptom2",
    "symptomversion2",
    "symptom3",
    "symptomversion3",
    "symptom4",
    "symptomversion4",
    "symptom5",
    "symptomversion5",
]
SYM_NUM = [
    "symptomversion1",
    "symptomversion2",
    "symptomversion3",
    "symptomversion4",
    "symptomversion5",
]

SPECS = {
    "raw_vaers_data": {
        "cols": DATA_COLS,
        "num": DATA_NUM,
        "surrogate": False,
        "source_file": True,
    },
    "raw_vaers_vax": {
        "cols": VAX_COLS,
        "num": [],
        "surrogate": True,
        "source_file": False,
    },
    "raw_vaers_symptoms": {
        "cols": SYM_COLS,
        "num": SYM_NUM,
        "surrogate": True,
        "source_file": False,
    },
}


def _read_csv(path: str):
    import pandas as pd

    df = pd.read_csv(
        path,
        dtype=str,
        encoding="latin-1",
        keep_default_na=False,
        na_values=[""],
        engine="python",
        on_bad_lines="warn",
    )
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def _prepare(df, spec, batch_id: str, source_file: str):
    import pandas as pd

    df = df.reindex(columns=spec["cols"])  # keep only known cols, in order
    for c in spec["num"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if spec["surrogate"]:
        df["_row_id"] = [uuid.uuid4().hex for _ in range(len(df))]
    df["_load_batch_id"] = batch_id
    if spec["source_file"]:
        df["_source_file"] = source_file
    df["_ingested_at"] = pd.Timestamp.utcnow()
    return df


def upload_to_gcs(cfg: Settings, local_path: str) -> str:
    if not cfg.bucket:
        return ""
    client = storage_client(cfg)
    blob_name = f"raw/{os.path.basename(local_path)}"
    client.bucket(cfg.bucket).blob(blob_name).upload_from_filename(local_path)
    return f"gs://{cfg.bucket}/{blob_name}"


def load_file(
    cfg: Settings, bq: BigQuery, local_path: str, table: str, batch_id: str
) -> int:
    from google.cloud import bigquery

    gcs_uri = upload_to_gcs(cfg, local_path)  # lineage copy
    df = _prepare(_read_csv(local_path), SPECS[table], batch_id, gcs_uri or local_path)
    job = bq.client.load_table_from_dataframe(
        df,
        cfg.table(table),
        job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND"),
    )
    job.result()
    return len(df)


def load_all(cfg: Settings, data_csv: str, vax_csv: str, symptoms_csv: str) -> dict:
    bq = BigQuery(cfg)
    batch_id = uuid.uuid4().hex
    counts = {
        "raw_vaers_data": load_file(cfg, bq, data_csv, "raw_vaers_data", batch_id),
        "raw_vaers_vax": load_file(cfg, bq, vax_csv, "raw_vaers_vax", batch_id),
        "raw_vaers_symptoms": load_file(
            cfg, bq, symptoms_csv, "raw_vaers_symptoms", batch_id
        ),
    }
    counts["batch_id"] = batch_id
    return counts


def build_reference_and_slice(cfg: Settings) -> dict:
    """Derive scope + PT list and (re)create the demo slice view."""
    bq = BigQuery(cfg)
    ds = cfg.ds
    manu_clause = "AND vax_manu = @manu" if cfg.scope_manufacturer else ""
    params = {"label": f"{cfg.scope_vax_type} family", "vt": cfg.scope_vax_type}
    if cfg.scope_manufacturer:
        params["manu"] = cfg.scope_manufacturer

    # 1) product scope (single family)
    bq.query(
        f"""
        INSERT INTO `{ds}.ref_product_scope` (scope_label, vax_type, vax_name, vax_manu, in_scope, notes)
        SELECT @label, vax_type, vax_name, ANY_VALUE(vax_manu), TRUE, 'auto-derived'
        FROM `{ds}.raw_vaers_vax`
        WHERE vax_type = @vt {manu_clause}
          AND vax_name NOT IN (SELECT vax_name FROM `{ds}.ref_product_scope`)
        GROUP BY vax_type, vax_name
    """,
        params,
    )

    # 2) MedDRA PT list, restricted to in-scope cases (coding target + grounding corpus)
    bq.query(f"""
        INSERT INTO `{ds}.ref_meddra_pt` (pt_term, meddra_version, occurrence_count, indexed_in_vector_search)
        SELECT s.pt_term, ANY_VALUE(CAST(s.meddra_version AS STRING)), COUNT(*), FALSE
        FROM `{ds}.vw_symptoms_long` s
        WHERE s.vaers_id IN (
          SELECT DISTINCT v.vaers_id FROM `{ds}.raw_vaers_vax` v
          JOIN `{ds}.ref_product_scope` sc ON sc.vax_name = v.vax_name AND sc.in_scope
        )
        AND s.pt_term NOT IN (SELECT pt_term FROM `{ds}.ref_meddra_pt`)
        GROUP BY s.pt_term
    """)

    # 3) demo slice view: in-scope, narrative-rich cases
    bq.query(f"""
        CREATE OR REPLACE VIEW `{ds}.vw_demo_slice` AS
        SELECT d.vaers_id, d.symptom_text, d.recvdate
        FROM `{ds}.raw_vaers_data` d
        WHERE LENGTH(d.symptom_text) >= {int(cfg.min_narrative_chars)}
          AND EXISTS (
            SELECT 1 FROM `{ds}.raw_vaers_vax` v
            JOIN `{ds}.ref_product_scope` sc ON sc.vax_name = v.vax_name AND sc.in_scope
            WHERE v.vaers_id = d.vaers_id)
    """)

    scope_n = bq.query_one(
        f"SELECT COUNT(*) AS n FROM `{ds}.ref_product_scope` WHERE in_scope"
    )["n"]
    pt_n = bq.query_one(f"SELECT COUNT(*) AS n FROM `{ds}.ref_meddra_pt`")["n"]
    slice_n = bq.query_one(f"SELECT COUNT(*) AS n FROM `{ds}.vw_demo_slice`")["n"]
    return {
        "in_scope_products": scope_n,
        "meddra_pts": pt_n,
        "demo_slice_cases": slice_n,
    }
