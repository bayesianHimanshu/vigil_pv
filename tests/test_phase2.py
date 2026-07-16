"""Offline verification for Phase 2 (no GCP).

    python tests/test_phase2.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import ValidationError
from vigil.contracts import (CodingOutput, CodingResult, CodedEvent,
                             ExtractionResult, ExtractedCase, Patient, ExtractedEvent, Product)
from vigil import normalize as nz
from vigil.llm import LLMMeta
from vigil.coding_agent import CodingAgent
from vigil.grounding import NullGrounder
from vigil.pipeline import run_case
from vigil.config import Settings, PIPELINE_VERSION_PHASE2

passed = 0
def check(name, cond):
    global passed
    assert cond, f"FAILED: {name}"
    passed += 1
    print(f"  ok  {name}")


# ---- 1. coding contracts ----
print("contracts:")
co = CodingOutput(result=CodingResult(
        coded=[CodedEvent(verbatim="fever", meddra_pt="Pyrexia", confidence=0.95)],
        uncoded=["odd sensation"]),
     confidence=0.9)
check("coding output parses", co.result.coded[0].meddra_pt == "Pyrexia")
try:
    CodedEvent(verbatim="x", meddra_pt="Y", confidence=2.0); ok = False
except ValidationError:
    ok = True
check("coded confidence > 1 rejected", ok)


# ---- 2. F1 helper (mirrors vw_eval_case) ----
print("coding_prf:")
m = nz.coding_prf(["Headache", "Pyrexia"], ["headache", "Chills"])
check("tp/fp/fn correct", (m["tp"], m["fp"], m["fn"]) == (1, 1, 1))
check("f1 = 0.5", abs(m["f1"] - 0.5) < 1e-9)
check("normalization case-insensitive", nz.coding_prf(["PYREXIA"], ["pyrexia"])["f1"] == 1.0)
check("empty gold -> recall None", nz.coding_prf(["A"], [])["recall"] is None)


# ---- 3. coding agent (fake llm + grounder) ----
print("coding agent:")
class FakeLLM:
    model = "gemini-3-flash"
    def __init__(self): self.seen_user = None
    def generate(self, *, system, user, schema, temperature=0.0):
        self.seen_user = user
        out = schema(result={"coded": [{"verbatim": "fever", "meddra_pt": "Pyrexia", "confidence": 0.9}],
                             "uncoded": []}, confidence=0.88)
        return out, LLMMeta(model=self.model, input_tokens=50, output_tokens=20, latency_ms=300)

class RecordingGrounder:
    def __init__(self): self.called_with = None
    def ground(self, verbatims):
        self.called_with = verbatims
        return {v: ["Pyrexia", "Body temperature increased"] for v in verbatims}

fl, gr = FakeLLM(), RecordingGrounder()
agent = CodingAgent(fl, gr)
out, meta = agent.code("V1", ["fever"])
check("grounder invoked with events", gr.called_with == ["fever"])
check("candidates appear in prompt", "Pyrexia" in fl.seen_user)
check("coding result returned", out.result.coded[0].meddra_pt == "Pyrexia")
check("empty events short-circuits (no LLM call)",
      CodingAgent(FakeLLM(), NullGrounder()).code("V2", [])[0].result.coded == [])


# ---- 4. two-agent pipeline ----
print("pipeline (phase 2):")
class FakeExtractor:
    name, version, prompt_version = "extraction", "extraction@0.1.0", "extract-v1"
    def extract(self, vaers_id, narrative):
        case = ExtractedCase(patient=Patient(age_years=30, sex="male"),
                             products=[Product(name="COVID19 (MODERNA)", role="suspect")],
                             events=[ExtractedEvent(verbatim="fever"), ExtractedEvent(verbatim="headache")])
        return ExtractionResult(case=case, confidence=0.9), \
            LLMMeta(model="gemini-3-flash", input_tokens=100, output_tokens=60, latency_ms=800)

class FakeCoder:
    name, version, prompt_version = "coding", "coding@0.1.0", "code-v1"
    def __init__(self, uncoded=None): self._uncoded = uncoded or []
    def code(self, vaers_id, events):
        coded = [{"verbatim": "fever", "meddra_pt": "Pyrexia", "confidence": 0.95},
                 {"verbatim": "headache", "meddra_pt": "Headache", "confidence": 0.97}]
        return CodingOutput(result=CodingResult(coded=[CodedEvent(**c) for c in coded],
                                                uncoded=self._uncoded), confidence=0.93), \
            LLMMeta(model="gemini-3-flash", input_tokens=70, output_tokens=40, latency_ms=400)

class FakeBQ:
    def __init__(self): self.inserts = []
    def insert_row(self, table, row): self.inserts.append((table, row))

cfg = Settings(project="test", hitl_confidence_threshold=0.75)
bq = FakeBQ()
res = run_case(cfg, "V1", "Patient developed fever and headache.", "01012024",
               extractor=FakeExtractor(), coder=FakeCoder(), bq=bq,
               pipeline_version=PIPELINE_VERSION_PHASE2)

steps = [r for t, r in bq.inserts if t == "agt_step_event"]
case_row = [r for t, r in bq.inserts if t == "agt_case_output"][0]
run_row = [r for t, r in bq.inserts if t == "agt_run"][0]

check("two step events (extraction + coding)", len(steps) == 2)
check("step seq ordering", [s["seq"] for s in steps] == [1, 2])
check("agent names recorded", [s["agent_name"] for s in steps] == ["extraction", "coding"])
check("coded_pts flattened", case_row["coded_pts"] == ["Pyrexia", "Headache"])
check("coded_detail is valid JSON", len(json.loads(case_row["coded_detail"])["coded"]) == 2)
check("phase2 pipeline_version on case", case_row["pipeline_version"] == PIPELINE_VERSION_PHASE2)
check("model_config records both models",
      set(json.loads(run_row["model_config"]).keys()) == {"extraction_model", "coding_model"})
check("overall confidence is the min", abs(case_row["overall_confidence"] - 0.9) < 1e-9)
check("no HITL when confident and fully coded", case_row["hitl_required"] is False)
check("n_coded reported", res["n_coded"] == 2)

# uncoded events force HITL
bq2 = FakeBQ()
res2 = run_case(cfg, "V2", "Vague.", None, extractor=FakeExtractor(),
                coder=FakeCoder(uncoded=["odd sensation"]), bq=bq2,
                pipeline_version=PIPELINE_VERSION_PHASE2)
check("uncoded events trigger HITL", res2["hitl_required"] is True)

# extraction-only still works (Phase 1 path)
bq3 = FakeBQ()
run_case(cfg, "V3", "text", None, extractor=FakeExtractor(), bq=bq3)
check("phase-1 path: one step event, empty coded_pts",
      len([r for t, r in bq3.inserts if t == "agt_step_event"]) == 1 and
      [r for t, r in bq3.inserts if t == "agt_case_output"][0]["coded_pts"] == [])

print(f"\nALL {passed} CHECKS PASSED")
