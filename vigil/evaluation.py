"""Evaluation: extraction concordance vs human ground truth.

Creates a live view comparing the agent's extracted demographics/dates
against vw_gt_case, then a one-row scorecard. Mirrors the Python rules in
normalize.py (sex mapping, +/-1yr age tolerance).
"""
from __future__ import annotations
from .config import Settings


def eval_view_sql(cfg: Settings) -> str:
    ds = cfg.ds
    return f"""
CREATE OR REPLACE VIEW `{ds}.vw_eval_extraction` AS
WITH a AS (
  SELECT
    run_id, vaers_id,
    LOWER(JSON_VALUE(extracted, '$.patient.sex'))                       AS x_sex,
    SAFE_CAST(JSON_VALUE(extracted, '$.patient.age_years') AS FLOAT64)  AS x_age,
    JSON_VALUE(extracted, '$.onset_date')                              AS x_onset,
    ARRAY_LENGTH(JSON_QUERY_ARRAY(extracted, '$.events'))               AS x_n_events
  FROM `{ds}.agt_case_output`
)
SELECT
  a.run_id, a.vaers_id,
  a.x_sex, a.x_age, a.x_onset, a.x_n_events,
  CASE gc.sex WHEN 'M' THEN 'male' WHEN 'F' THEN 'female' ELSE 'unknown' END AS gt_sex,
  gc.age_yrs AS gt_age,
  CAST(gc.onset_date AS STRING) AS gt_onset,
  gc.n_coded_pts AS gt_n_pts,
  (a.x_sex = CASE gc.sex WHEN 'M' THEN 'male' WHEN 'F' THEN 'female' ELSE 'unknown' END) AS sex_match,
  (a.x_age IS NOT NULL AND gc.age_yrs IS NOT NULL AND ABS(a.x_age - gc.age_yrs) <= 1) AS age_match,
  (a.x_onset IS NOT NULL AND a.x_onset = CAST(gc.onset_date AS STRING)) AS onset_match
FROM a
JOIN `{ds}.vw_gt_case` gc USING (vaers_id);
"""


def scorecard_sql(cfg: Settings) -> str:
    ds = cfg.ds
    return f"""
SELECT
  COUNT(*)                                          AS n_cases,
  ROUND(AVG(IF(sex_match, 1, 0)), 4)                AS sex_accuracy,
  ROUND(AVG(IF(age_match, 1, 0)), 4)                AS age_accuracy,
  ROUND(AVG(IF(onset_match, 1, 0)), 4)              AS onset_accuracy,
  ROUND(CORR(x_n_events, gt_n_pts), 4)              AS event_count_corr
FROM `{ds}.vw_eval_extraction`;
"""


def coding_scorecard_sql(cfg: Settings) -> str:
    """Headline Phase 2 metric: MedDRA coding concordance vs human coders.

    Reads vw_eval_dashboard (defined in data_model.sql), filtered to the
    given pipeline_version (@pv). Seriousness accuracy is omitted here - it
    becomes meaningful in Phase 3 when the assessment agent runs.
    """
    ds = cfg.ds
    return f"""
SELECT pipeline_version, n_cases, mean_precision, mean_recall, mean_coding_f1
FROM `{ds}.vw_eval_dashboard`
WHERE pipeline_version = @pv
"""


def coding_worst_cases_sql(cfg: Settings) -> str:
    """Lowest-F1 cases for error review (drill-down from vw_eval_case)."""
    ds = cfg.ds
    return f"""
SELECT vaers_id, tp, fp, fn, ROUND(f1, 3) AS f1
FROM `{ds}.vw_eval_case`
WHERE pipeline_version = @pv
ORDER BY f1 ASC
LIMIT 20
"""


def phase3_scorecard_sql(cfg: Settings) -> str:
    """Phase 3 headline: coding F1 + seriousness accuracy vs human coders.

    Seriousness accuracy becomes meaningful now that the assessment agent
    populates agt_case_output.seriousness (vw_eval_case reads it).
    """
    ds = cfg.ds
    return f"""
SELECT pipeline_version, n_cases, mean_coding_f1, seriousness_accuracy
FROM `{ds}.vw_eval_dashboard`
WHERE pipeline_version = @pv
"""


def causality_distribution_sql(cfg: Settings) -> str:
    """WHO-UMC causality category distribution (shown, not scored)."""
    ds = cfg.ds
    return f"""
SELECT JSON_VALUE(causality, '$.category') AS category, COUNT(*) AS n
FROM `{ds}.agt_case_output`
WHERE pipeline_version = @pv AND causality IS NOT NULL
GROUP BY category
ORDER BY n DESC
"""
