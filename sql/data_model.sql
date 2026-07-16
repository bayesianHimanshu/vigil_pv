CREATE TABLE pv_vigil.raw_vaers_data (
  vaers_id      STRING  OPTIONS(description="VAERS report id; links all three files"),
  recvdate      STRING  OPTIONS(description="Date received (MMDDYYYY string)"),
  state         STRING,
  age_yrs       FLOAT64,
  cage_yr       FLOAT64,
  cage_mo       FLOAT64,
  sex           STRING  OPTIONS(description="M / F / blank"),
  rpt_date      STRING,
  symptom_text  STRING  OPTIONS(description="Free-text adverse-event narrative - the agent pipeline INPUT"),
  died          STRING  OPTIONS(description="'Y' if patient died (seriousness criterion)"),
  datedied      STRING,
  l_threat      STRING  OPTIONS(description="'Y' if life-threatening (seriousness criterion)"),
  er_visit      STRING,
  hospital      STRING  OPTIONS(description="'Y' if hospitalized (seriousness criterion)"),
  hospdays      FLOAT64,
  x_stay        STRING,
  disable       STRING  OPTIONS(description="'Y' if disability (seriousness criterion)"),
  recovd        STRING  OPTIONS(description="Recovered: Y / N / U"),
  vax_date      STRING  OPTIONS(description="Vaccination date (MMDDYYYY string)"),
  onset_date    STRING  OPTIONS(description="Symptom onset date (MMDDYYYY string)"),
  numdays       FLOAT64 OPTIONS(description="Days from vaccination to onset"),
  lab_data      STRING,
  v_adminby     STRING,
  v_fundby      STRING,
  other_meds    STRING,
  cur_ill       STRING,
  history       STRING,
  prior_vax     STRING,
  splttype      STRING  OPTIONS(description="Manufacturer/foreign report identifier"),
  form_vers     STRING,
  todays_date   STRING,
  birth_defect  STRING  OPTIONS(description="'Y' if congenital anomaly (seriousness criterion)"),
  ofc_visit     STRING,
  er_ed_visit   STRING,
  allergies     STRING,
  _ingested_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  _load_batch_id STRING,
  _source_file  STRING,
  PRIMARY KEY (vaers_id) NOT ENFORCED
)
PARTITION BY DATE(_ingested_at)
CLUSTER BY vaers_id
OPTIONS(description="Raw VAERSDATA: one row per case, incl. narrative and seriousness flags");


CREATE TABLE pv_vigil.raw_vaers_vax (
  _row_id          STRING DEFAULT GENERATE_UUID(),
  vaers_id         STRING,
  vax_type         STRING OPTIONS(description="Vaccine category, e.g. COVID19, FLU3"),
  vax_manu         STRING OPTIONS(description="Manufacturer"),
  vax_lot          STRING,
  vax_dose_series  STRING,
  vax_route        STRING,
  vax_site         STRING,
  vax_name         STRING OPTIONS(description="Specific product name"),
  _ingested_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  _load_batch_id   STRING,
  PRIMARY KEY (_row_id) NOT ENFORCED,
  FOREIGN KEY (vaers_id) REFERENCES pv_vigil.raw_vaers_data(vaers_id) NOT ENFORCED
)
CLUSTER BY vaers_id
OPTIONS(description="Raw VAERSVAX: products per case (1-to-many)");


CREATE TABLE pv_vigil.raw_vaers_symptoms (
  _row_id          STRING DEFAULT GENERATE_UUID(),
  vaers_id         STRING,
  symptom1         STRING, symptomversion1 FLOAT64,
  symptom2         STRING, symptomversion2 FLOAT64,
  symptom3         STRING, symptomversion3 FLOAT64,
  symptom4         STRING, symptomversion4 FLOAT64,
  symptom5         STRING, symptomversion5 FLOAT64,
  _ingested_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  _load_batch_id   STRING,
  PRIMARY KEY (_row_id) NOT ENFORCED,
  FOREIGN KEY (vaers_id) REFERENCES pv_vigil.raw_vaers_data(vaers_id) NOT ENFORCED
)
CLUSTER BY vaers_id
OPTIONS(description="Raw VAERSSYMPTOMS: up to 5 human-coded MedDRA PTs per row, many rows per case");



-- ZONE 2 - REFERENCE / DERIVED


CREATE TABLE pv_vigil.ref_product_scope (
  scope_label  STRING OPTIONS(description="Demo scope name, e.g. 'COVID19 mRNA family'"),
  vax_type     STRING,
  vax_name     STRING,
  vax_manu     STRING,
  in_scope     BOOL   OPTIONS(description="TRUE = part of the single product family under study"),
  notes        STRING,
  PRIMARY KEY (vax_name) NOT ENFORCED
)
OPTIONS(description="Defines the single product family in scope for the demo");


CREATE TABLE pv_vigil.ref_meddra_pt (
  pt_term                  STRING OPTIONS(description="MedDRA Preferred Term (derived from loaded VAERS data - published terms only)"),
  meddra_version           STRING,
  occurrence_count         INT64  OPTIONS(description="Frequency across the loaded set"),
  first_seen_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  indexed_in_vector_search BOOL   OPTIONS(description="TRUE once pushed to Vertex AI Search / Vector Search for grounding"),
  PRIMARY KEY (pt_term) NOT ENFORCED
)
OPTIONS(description="Coding target + grounding corpus. Embeddings are indexed externally in Vertex AI Vector Search; this table holds the canonical term list and metadata");



-- ZONE 3 - GROUND TRUTH  (live VIEWS - the human-curated answer key)


-- Unpivot the 5 wide MedDRA slots into long form (vaers_id, pt_term, version)
CREATE VIEW pv_vigil.vw_symptoms_long AS
SELECT vaers_id, pt_term, meddra_version
FROM (
  SELECT vaers_id, symptom1 AS pt_term, symptomversion1 AS meddra_version FROM pv_vigil.raw_vaers_symptoms
  UNION ALL SELECT vaers_id, symptom2, symptomversion2 FROM pv_vigil.raw_vaers_symptoms
  UNION ALL SELECT vaers_id, symptom3, symptomversion3 FROM pv_vigil.raw_vaers_symptoms
  UNION ALL SELECT vaers_id, symptom4, symptomversion4 FROM pv_vigil.raw_vaers_symptoms
  UNION ALL SELECT vaers_id, symptom5, symptomversion5 FROM pv_vigil.raw_vaers_symptoms
)
WHERE pt_term IS NOT NULL AND TRIM(pt_term) != '';

-- Ground-truth coded PTs per case (the coding-agent answer key)
CREATE VIEW pv_vigil.vw_gt_pt AS
SELECT DISTINCT
  vaers_id,
  UPPER(TRIM(pt_term)) AS pt_term,
  meddra_version
FROM pv_vigil.vw_symptoms_long;

-- Ground-truth case facts (the extraction + assessment answer key)
CREATE VIEW pv_vigil.vw_gt_case AS
WITH prod AS (
  SELECT vaers_id, COUNT(*) AS n_products
  FROM pv_vigil.raw_vaers_vax GROUP BY vaers_id
),
pts AS (
  SELECT vaers_id, COUNT(*) AS n_pts
  FROM pv_vigil.vw_gt_pt GROUP BY vaers_id
)
SELECT
  d.vaers_id,
  d.age_yrs,
  d.sex,
  d.state,
  SAFE.PARSE_DATE('%m%d%Y', d.vax_date)   AS vax_date,
  SAFE.PARSE_DATE('%m%d%Y', d.onset_date) AS onset_date,
  d.numdays                               AS days_to_onset,
  SAFE.PARSE_DATE('%m%d%Y', d.recvdate)   AS received_date,
  (d.died        = 'Y')                   AS died,
  (d.l_threat    = 'Y')                   AS life_threatening,
  (d.hospital    = 'Y')                   AS hospitalized,
  (d.disable     = 'Y')                   AS disabled,
  (d.birth_defect= 'Y')                   AS birth_defect,
  (d.died='Y' OR d.l_threat='Y' OR d.hospital='Y' OR d.disable='Y' OR d.birth_defect='Y') AS serious,
  d.recovd                                AS recovered,
  COALESCE(prod.n_products, 0)            AS n_products,
  COALESCE(pts.n_pts, 0)                  AS n_coded_pts
FROM pv_vigil.raw_vaers_data d
LEFT JOIN prod USING (vaers_id)
LEFT JOIN pts  USING (vaers_id);



-- ZONE 4 - AGENT OUTPUT  (APPEND-ONLY tables = system of record + audit)


-- One row per pipeline execution
CREATE TABLE pv_vigil.agt_run (
  run_id             STRING DEFAULT GENERATE_UUID(),
  vaers_id           STRING,
  pipeline_version   STRING OPTIONS(description="e.g. 'pipeline@1.3.0' - enables version-over-version eval"),
  model_config       JSON   OPTIONS(description="Models + params used, e.g. {flash, pro, temps}"),
  status             STRING OPTIONS(description="running | completed | failed | in_review | finalized"),
  overall_confidence FLOAT64,
  hitl_required      BOOL,
  started_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  finished_at        TIMESTAMP,
  PRIMARY KEY (run_id) NOT ENFORCED,
  FOREIGN KEY (vaers_id) REFERENCES pv_vigil.raw_vaers_data(vaers_id) NOT ENFORCED
)
PARTITION BY DATE(started_at)
CLUSTER BY vaers_id, pipeline_version
OPTIONS(description="Run-level metadata, one row per case processing run");

-- Immutable per-agent event log - the granular audit trail
CREATE TABLE pv_vigil.agt_step_event (
  event_id       STRING DEFAULT GENERATE_UUID(),
  run_id         STRING,
  vaers_id       STRING,
  seq            INT64  OPTIONS(description="Order of the step within the run"),
  agent_name     STRING OPTIONS(description="orchestrator|triage|extraction|coding|assessment|narrative_qc|signal"),
  agent_version  STRING,
  model          STRING OPTIONS(description="e.g. gemini-3-flash / gemini-3-pro"),
  prompt_version STRING,
  input_hash     STRING OPTIONS(description="Hash of the step input for reproducibility"),
  output         JSON   OPTIONS(description="Structured output of this agent step"),
  confidence     FLOAT64,
  input_tokens   INT64,
  output_tokens  INT64,
  latency_ms     INT64,
  created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (event_id) NOT ENFORCED,
  FOREIGN KEY (run_id) REFERENCES pv_vigil.agt_run(run_id) NOT ENFORCED
)
PARTITION BY DATE(created_at)
CLUSTER BY run_id, agent_name
OPTIONS(description="Append-only log of every agent invocation");

-- Assembled structured case per run (one snapshot row per run)
CREATE TABLE pv_vigil.agt_case_output (
  run_id             STRING,
  vaers_id           STRING,
  pipeline_version   STRING,
  model              STRING,
  extracted          JSON OPTIONS(description="{patient, products[], events[], dates, concomitant_meds[], history[]}"),
  coded_pts          ARRAY<STRING> OPTIONS(description="Agent-assigned MedDRA PTs (the coding-agent prediction)"),
  coded_detail       JSON OPTIONS(description="[{verbatim, meddra_pt, confidence}]"),
  seriousness        JSON OPTIONS(description="{criteria_met[], serious: bool}"),
  causality          JSON OPTIONS(description="{method, category, rationale} - shown, not scored"),
  narrative          STRING,
  overall_confidence FLOAT64,
  hitl_required      BOOL,
  created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (run_id) NOT ENFORCED,
  FOREIGN KEY (run_id) REFERENCES pv_vigil.agt_run(run_id) NOT ENFORCED,
  FOREIGN KEY (vaers_id) REFERENCES pv_vigil.raw_vaers_data(vaers_id) NOT ENFORCED
)
PARTITION BY DATE(created_at)
CLUSTER BY vaers_id, pipeline_version
OPTIONS(description="Final assembled case per run; append-only (re-runs get a new run_id)");

-- Human-in-the-loop decisions - append-only (Part 11-style review trail)
CREATE TABLE pv_vigil.agt_human_review_event (
  review_id    STRING DEFAULT GENERATE_UUID(),
  run_id       STRING,
  vaers_id     STRING,
  reviewer_id  STRING,
  action       STRING OPTIONS(description="approve | edit | reject | escalate"),
  field_path   STRING OPTIONS(description="Field touched, e.g. 'coded_pts' or 'seriousness.serious'"),
  old_value    JSON,
  new_value    JSON,
  rationale    STRING,
  reviewed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (review_id) NOT ENFORCED,
  FOREIGN KEY (run_id) REFERENCES pv_vigil.agt_run(run_id) NOT ENFORCED
)
PARTITION BY DATE(reviewed_at)
CLUSTER BY run_id
OPTIONS(description="Append-only record of every human review action");



-- ZONE 5 - EVALUATION  (live VIEWS: agent output vs human ground truth)


-- Per-case coding F1 + seriousness match, by run
CREATE VIEW pv_vigil.vw_eval_case AS
WITH a AS (
  SELECT
    run_id, vaers_id, pipeline_version,
    ARRAY(SELECT UPPER(TRIM(p)) FROM UNNEST(coded_pts) p WHERE p IS NOT NULL) AS agent_pts,
    SAFE_CAST(JSON_VALUE(seriousness, '$.serious') AS BOOL) AS agent_serious
  FROM pv_vigil.agt_case_output
),
g AS (
  SELECT vaers_id, ARRAY_AGG(DISTINCT pt_term) AS gt_pts
  FROM pv_vigil.vw_gt_pt GROUP BY vaers_id
),
counts AS (
  SELECT
    a.run_id, a.vaers_id, a.pipeline_version, a.agent_serious,
    (SELECT COUNT(*) FROM UNNEST(a.agent_pts) p WHERE p IN UNNEST(g.gt_pts)) AS tp,
    (SELECT COUNT(*) FROM UNNEST(a.agent_pts) p WHERE p NOT IN UNNEST(g.gt_pts)) AS fp,
    (SELECT COUNT(*) FROM UNNEST(g.gt_pts) p WHERE p NOT IN UNNEST(a.agent_pts)) AS fn
  FROM a JOIN g USING (vaers_id)
)
SELECT
  c.run_id, c.vaers_id, c.pipeline_version,
  c.tp, c.fp, c.fn,
  SAFE_DIVIDE(c.tp, c.tp + c.fp) AS precision,
  SAFE_DIVIDE(c.tp, c.tp + c.fn) AS recall,
  SAFE_DIVIDE(2 * c.tp, 2 * c.tp + c.fp + c.fn) AS f1,
  (c.agent_serious = gc.serious) AS seriousness_match,
  c.agent_serious, gc.serious AS gt_serious
FROM counts c
JOIN pv_vigil.vw_gt_case gc USING (vaers_id);

-- Aggregate scorecard per pipeline version (the "concordance vs coders" headline)
CREATE VIEW pv_vigil.vw_eval_dashboard AS
SELECT
  pipeline_version,
  COUNT(*)                                   AS n_cases,
  ROUND(AVG(precision), 4)                   AS mean_precision,
  ROUND(AVG(recall), 4)                      AS mean_recall,
  ROUND(AVG(f1), 4)                          AS mean_coding_f1,
  ROUND(AVG(IF(seriousness_match, 1, 0)), 4) AS seriousness_accuracy
FROM pv_vigil.vw_eval_case
GROUP BY pipeline_version;



-- ZONE 6 - SIGNAL DETECTION  (live VIEW: disproportionality, PRR / ROR)
-- 2x2 per in-scope product vs each event PT, over the loaded set.


CREATE VIEW pv_vigil.vw_signal_metrics AS
WITH
-- one row per case, flagged for the in-scope product family
case_drug AS (
  SELECT DISTINCT
    o.vaers_id,
    EXISTS (
      SELECT 1 FROM pv_vigil.raw_vaers_vax v
      JOIN pv_vigil.ref_product_scope s ON s.vax_name = v.vax_name AND s.in_scope
      WHERE v.vaers_id = o.vaers_id
    ) AS is_scope_drug
  FROM pv_vigil.agt_case_output o
),
-- one row per (case, event) from the agent's coding
case_event AS (
  SELECT DISTINCT o.vaers_id, UPPER(TRIM(p)) AS event_pt
  FROM pv_vigil.agt_case_output o, UNNEST(o.coded_pts) p
  WHERE p IS NOT NULL AND TRIM(p) != ''
),
total AS (SELECT COUNT(*) AS n FROM case_drug),
cells AS (
  SELECT
    e.event_pt,
    COUNTIF(d.is_scope_drug)                          AS a,   -- drug & event
    COUNTIF(NOT d.is_scope_drug)                       AS c    -- not-drug & event
  FROM case_event e
  JOIN case_drug d USING (vaers_id)
  GROUP BY e.event_pt
),
drug_totals AS (
  SELECT
    COUNTIF(is_scope_drug)     AS n_drug,      -- a + b
    COUNTIF(NOT is_scope_drug) AS n_not_drug   -- c + d
  FROM case_drug
)
SELECT
  cells.event_pt,
  cells.a,
  (dt.n_drug - cells.a)                    AS b,
  cells.c,
  (dt.n_not_drug - cells.c)                AS d,
  total.n                                  AS n_total,
  ROUND(SAFE_DIVIDE(cells.a * 1.0 / dt.n_drug,
                    cells.c * 1.0 / dt.n_not_drug), 3)            AS prr,
  ROUND(SAFE_DIVIDE(cells.a * (dt.n_not_drug - cells.c),
                    (dt.n_drug - cells.a) * cells.c), 3)         AS ror,
  -- conventional screening threshold: PRR>=2, a>=3
  (SAFE_DIVIDE(cells.a * 1.0 / dt.n_drug,
               cells.c * 1.0 / dt.n_not_drug) >= 2 AND cells.a >= 3) AS signal_flag
FROM cells
CROSS JOIN drug_totals dt
CROSS JOIN total
ORDER BY prr DESC;



-- CURATED VIEWS  (for the Gemini Enterprise UI surfaces)


-- Review queue: latest run per case that needs a human, not yet actioned
CREATE VIEW pv_vigil.vw_review_queue AS
WITH latest AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY vaers_id ORDER BY created_at DESC) AS rn
  FROM pv_vigil.agt_case_output
)
SELECT
  l.vaers_id, l.run_id, l.pipeline_version, l.overall_confidence,
  l.narrative, l.coded_pts, l.seriousness, l.created_at
FROM latest l
WHERE l.rn = 1
  AND l.hitl_required
  AND NOT EXISTS (
    SELECT 1 FROM pv_vigil.agt_human_review_event r
    WHERE r.run_id = l.run_id AND r.action IN ('approve','reject')
  )
ORDER BY l.overall_confidence ASC;

-- Full case view: raw + product + latest agent output + ground truth + eval
CREATE VIEW pv_vigil.vw_case_full AS
WITH latest AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY vaers_id ORDER BY created_at DESC) AS rn
  FROM pv_vigil.agt_case_output
)
SELECT
  d.vaers_id,
  d.symptom_text,
  gc.age_yrs, gc.sex, gc.serious AS gt_serious, gc.n_coded_pts,
  o.run_id, o.pipeline_version,
  o.extracted, o.coded_pts, o.seriousness, o.causality, o.narrative,
  o.overall_confidence, o.hitl_required,
  ev.f1 AS coding_f1, ev.precision AS coding_precision,
  ev.recall AS coding_recall, ev.seriousness_match
FROM pv_vigil.raw_vaers_data d
LEFT JOIN pv_vigil.vw_gt_case gc USING (vaers_id)
LEFT JOIN latest o ON o.vaers_id = d.vaers_id AND o.rn = 1
LEFT JOIN pv_vigil.vw_eval_case ev ON ev.run_id = o.run_id;



-- OPERATIONAL STATE - Firestore  (document model; NOT BigQuery)
-- ---------------------------------------------------------------------
-- BigQuery above is the analytical system of record + audit trail.
-- Firestore holds low-latency, mutable workflow state that drives the
-- live UI (the one place mutation is allowed; every state transition is
-- ALSO appended to agt_step_event for the immutable record).
--
-- Collection:  cases/{vaers_id}
--   {
--     vaers_id:          string,
--     current_status:    string,   // received|triaging|extracting|coding|
--                                   //   assessing|drafting|in_review|finalized|failed
--     current_run_id:    string,
--     overall_confidence:number,
--     hitl_required:     bool,
--     assigned_reviewer: string|null,
--     lock:              { holder: string|null, expires_at: timestamp },
--     updated_at:        timestamp
--   }
--
-- Sub-collection:  cases/{vaers_id}/events/{event_id}
--   { seq, agent_name, status, confidence, ts }   // mirrors pipeline progress
--
-- Collection:  pipeline_versions/{version}
--   { models, prompt_versions, deployed_at, active: bool }

