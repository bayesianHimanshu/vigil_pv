#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Project VIGIL - end-to-end GCP deploy.
#
#   1. terraform apply        (infra: APIs, IAM, KMS/CMEK, GCS, BigQuery dataset,
#                              Firestore, Vertex AI Search data store)
#   2. write + source .env    (from terraform outputs)
#   3. apply BigQuery DDL      (sql/data_model.sql -> 9 tables + 8 views)
#   4. [optional] load VAERS   (data/*.csv -> raw tables -> reference + slice)
#   5. [optional] deploy agent (orchestrator + signal -> Vertex AI Agent Engine)
#
# Prereqs:
#   - gcloud auth application-default login   (Terraform + clients use ADC)
#   - a Python env with -r requirements.txt installed (and, for step 5,
#     -r deploy/requirements-deploy.txt)
#
# Usage:
#   deploy/deploy.sh                 # infra + DDL
#   deploy/deploy.sh --load          # ... + load VAERS CSVs from data/
#   deploy/deploy.sh --load --agent  # ... + deploy to Agent Engine
#   deploy/deploy.sh --plan          # terraform plan only, stop
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT/terraform"
ENV_FILE="$ROOT/.env"

DO_LOAD=0
DO_AGENT=0
PLAN_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --load)  DO_LOAD=1 ;;
    --agent) DO_AGENT=1 ;;
    --plan)  PLAN_ONLY=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

echo "==> Checking Application Default Credentials"
if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
  echo "ERROR: ADC not valid. Run:  gcloud auth application-default login" >&2
  exit 1
fi

echo "==> Terraform init"
terraform -chdir="$TF_DIR" init -input=false

if [[ "$PLAN_ONLY" == 1 ]]; then
  terraform -chdir="$TF_DIR" plan -input=false
  exit 0
fi

echo "==> Terraform apply"
terraform -chdir="$TF_DIR" apply -input=false -auto-approve

echo "==> Writing $ENV_FILE from terraform outputs"
terraform -chdir="$TF_DIR" output -raw runtime_env > "$ENV_FILE"
cat "$ENV_FILE"
# shellcheck disable=SC1090
source "$ENV_FILE"

echo "==> Applying BigQuery DDL (sql/data_model.sql)"
( cd "$ROOT" && python -m scripts.apply_ddl )

if [[ "$DO_LOAD" == 1 ]]; then
  echo "==> Loading VAERS CSVs from data/"
  DATA=$(ls "$ROOT"/data/*VAERSDATA.csv 2>/dev/null | head -1 || true)
  VAX=$(ls "$ROOT"/data/*VAERSVAX.csv 2>/dev/null | head -1 || true)
  SYM=$(ls "$ROOT"/data/*VAERSSYMPTOMS.csv 2>/dev/null | head -1 || true)
  if [[ -z "$DATA" || -z "$VAX" || -z "$SYM" ]]; then
    echo "ERROR: expected *VAERSDATA.csv, *VAERSVAX.csv, *VAERSSYMPTOMS.csv in data/" >&2
    exit 1
  fi
  ( cd "$ROOT" && python -m scripts.phase0_load --data "$DATA" --vax "$VAX" --symptoms "$SYM" )
fi

if [[ "$DO_AGENT" == 1 ]]; then
  echo "==> Deploying agents to Vertex AI Agent Engine"
  AGENT_SA=$(terraform -chdir="$TF_DIR" output -raw agent_service_account)
  STAGING=$(terraform -chdir="$TF_DIR" output -raw staging_bucket)
  ( cd "$ROOT" && \
    VIGIL_AGENT_SA="$AGENT_SA" \
    VIGIL_STAGING_BUCKET="$STAGING" \
    python -m deploy.agent_engine_deploy )
fi

echo "==> Done."
echo "Next: configure the Gemini Enterprise surface (deploy/GEMINI-ENTERPRISE.md)."
