"""Local verification of the pure logic - runs with no GCP access.

    python tests/test_local.py

Exercises the contracts, the matching helpers, and the full pipeline
wiring (with a fake LLM + fake BigQuery), proving the append-only writes
and routing without touching the cloud.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import ValidationError
from vigil.contracts import ExtractionResult, ExtractedCase, Patient, ExtractedEvent, Product
from vigil import normalize as nz
from vigil.llm import LLMMeta
from vigil.pipeline import run_case
from vigil.config import Settings

passed = 0
def check(name, cond):
    global passed
    assert cond, f"FAILED: {name}"
    passed += 1
    print(f"  ok  {name}")


# ---- 1. contracts ----
print("contracts:")
good = ExtractionResult(case=ExtractedCase(patient=Patient(age_years=42, sex="female"),
                                           events=[ExtractedEvent(verbatim="severe headache")]),
                        confidence=0.9)
check("valid extraction parses", good.case.patient.sex.value == "female")
check("round-trips through JSON",
      ExtractionResult.model_validate_json(good.model_dump_json()).confidence == 0.9)
try:
    ExtractionResult(case=good.case, confidence=1.7); ok = False
except ValidationError:
    ok = True
check("confidence > 1 rejected", ok)
try:
    Patient(age_years=1, sex="female", junk="x"); ok = False
except ValidationError:
    ok = True
check("unknown field rejected (extra=forbid)", ok)


# ---- 2. matching helpers ----
print("normalize:")
check("sex M -> male matches 'male'", nz.sex_match("male", "M"))
check("sex mismatch", not nz.sex_match("female", "M"))
check("age within 1yr matches", nz.age_match(42.0, 42.4) is True)
check("age beyond tol fails", nz.age_match(42.0, 50.0) is False)
check("age unscorable when null", nz.age_match(None, 42.0) is None)
check("product recall loose match",
      nz.product_recall(["COVID19 (PFIZER-BIONTECH)"], ["covid19 pfizer-biontech"]) == 1.0)


# ---- 3. pipeline wiring (fakes) ----
print("pipeline:")
class FakeExtractor:
    name, version, prompt_version = "extraction", "extraction@0.1.0", "extract-v1"
    def __init__(self, conf): self._conf = conf
    def extract(self, vaers_id, narrative):
        case = ExtractedCase(patient=Patient(age_years=30, sex="male"),
                             products=[Product(name="COVID19 (MODERNA)", role="suspect")],
                             events=[ExtractedEvent(verbatim="fever"), ExtractedEvent(verbatim="chills")],
                             onset_date="2024-03-01")
        return (ExtractionResult(case=case, confidence=self._conf),
                LLMMeta(model="gemini-3-flash", input_tokens=120, output_tokens=80, latency_ms=900))

class FakeBQ:
    def __init__(self): self.inserts = []
    def insert_row(self, table, row): self.inserts.append((table, row))

cfg = Settings(project="test", hitl_confidence_threshold=0.75)

# high-confidence case -> no HITL
bq = FakeBQ()
res = run_case(cfg, "V1", "Patient developed fever and chills after dose.", "01012024",
               extractor=FakeExtractor(0.92), bq=bq)
tables = [t for t, _ in bq.inserts]
check("three append-only inserts", len(bq.inserts) == 3)
check("writes step/case/run", set(tables) == {"agt_step_event", "agt_case_output", "agt_run"})
check("no HITL at high confidence", res["hitl_required"] is False)
check("events counted", res["n_events"] == 2)

rows = {t: r for t, r in bq.inserts}
check("coded_pts empty in Phase 1", rows["agt_case_output"]["coded_pts"] == [])
check("extracted is valid JSON with events",
      len(json.loads(rows["agt_case_output"]["extracted"])["events"]) == 2)
check("step output is valid JSON", isinstance(json.loads(rows["agt_step_event"]["output"]), dict))
check("run status completed", rows["agt_run"]["status"] == "completed")
check("same run_id across rows",
      rows["agt_step_event"]["run_id"] == rows["agt_case_output"]["run_id"] == rows["agt_run"]["run_id"])

# low-confidence case -> HITL
bq2 = FakeBQ()
res2 = run_case(cfg, "V2", "Vague report.", None, extractor=FakeExtractor(0.40), bq=bq2)
check("HITL flagged at low confidence", res2["hitl_required"] is True)

# append-only: the fake exposes no update method
check("append-only (no update path)", not hasattr(FakeBQ, "update_row"))

print(f"\nALL {passed} CHECKS PASSED")
