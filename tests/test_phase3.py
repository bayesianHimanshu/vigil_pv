"""Offline verification for Phase 3 (no GCP).

    python tests/test_phase3.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import ValidationError
from vigil.contracts import (TriageOutput, AssessmentOutput, NarrativeQCOutput,
                             SeriousnessAssessment, CausalityAssessment, CausalityMethod,
                             ExtractionResult, ExtractedCase, Patient, ExtractedEvent, Product,
                             CodingOutput, CodingResult, CodedEvent)
from vigil.llm import LLMMeta
from vigil.assessment_agent import AssessmentAgent
from vigil.narrative_qc_agent import NarrativeQCAgent
from vigil.triage_agent import TriageAgent
from vigil.orchestrator import Orchestrator
from vigil.config import Settings, PIPELINE_VERSION_PHASE3

passed = 0
def check(name, cond):
    global passed
    assert cond, f"FAILED: {name}"
    passed += 1
    print(f"  ok  {name}")


# ---- 1. contracts ----
print("contracts:")
ao = AssessmentOutput(
    seriousness=SeriousnessAssessment(serious=True, criteria_met=["hospitalization"]),
    causality=CausalityAssessment(method="WHO-UMC", category="probable", rationale="temporal + plausible"),
    confidence=0.8)
check("assessment parses; WHO-UMC enum", ao.causality.method == CausalityMethod.who_umc)
try:
    CausalityAssessment(method="WHO-UMC", category="definitely", rationale="x"); ok = False
except ValidationError:
    ok = True
check("invalid causality category rejected", ok)
nq = NarrativeQCOutput(narrative="Pt ...", completeness={"completeness_score": 0.9, "gaps": []},
                       qc_flags=[{"type": "missing_field", "severity": "warning"}],
                       overall_confidence=0.85, hitl_recommended=False)
check("narrative+QC parses", nq.qc_flags[0].type.value == "missing_field")
check("triage parses", TriageOutput(valid=True, seriousness_screen={"serious": False},
                                    priority="standard", confidence=0.9).priority.value == "standard")


# ---- 2. agents (fake LLM) ----
print("agents:")
class FakeLLM:
    def __init__(self, model, builder): self.model = model; self._b = builder; self.seen = None
    def generate(self, *, system, user, schema, temperature=0.0):
        self.seen = user
        return self._b(schema), LLMMeta(model=self.model, input_tokens=40, output_tokens=20, latency_ms=200)

ex_case = ExtractedCase(patient=Patient(age_years=70, sex="female"),
                        products=[Product(name="COVID19 (PFIZER-BIONTECH)", role="suspect")],
                        events=[ExtractedEvent(verbatim="chest pain")],
                        onset_date="2024-02-02")
coded = CodingResult(coded=[CodedEvent(verbatim="chest pain", meddra_pt="Chest pain", confidence=0.9)])

assessor = AssessmentAgent(FakeLLM("gemini-3-pro", lambda s: s(
    seriousness={"serious": True, "criteria_met": ["hospitalization"]},
    causality={"method": "WHO-UMC", "category": "possible", "rationale": "temporal"},
    confidence=0.82)))
a_out, _ = assessor.assess("V1", extracted=ex_case, coded=coded)
check("assessment agent returns output", a_out.seriousness.serious is True)
check("coded PT used in assessment prompt", "Chest pain" in assessor._llm.seen)

narrator = NarrativeQCAgent(FakeLLM("gemini-3-pro", lambda s: s(
    narrative="A 70-year-old female ...",
    completeness={"completeness_score": 0.9, "gaps": []},
    qc_flags=[], overall_confidence=0.88, hitl_recommended=False)))
n_out, _ = narrator.run("V1", extracted=ex_case, coded=coded,
                        seriousness=a_out.seriousness, causality=a_out.causality)
check("narrative agent returns text", n_out.narrative.startswith("A 70-year-old"))


# ---- 3. full orchestrator chain ----
print("orchestrator (all five):")
class FakeTriage:
    name, version, prompt_version = "triage", "triage@0.1.0", "triage-v1"
    def triage(self, vaers_id, narrative, received_date=None):
        return TriageOutput(valid=True, seriousness_screen={"serious": True, "criteria_flagged": ["hospitalization"]},
                            priority="expedited", confidence=0.9), \
            LLMMeta(model="gemini-3-flash", input_tokens=30, output_tokens=10, latency_ms=100)
class FakeExtractor:
    name, version, prompt_version = "extraction", "extraction@0.1.0", "extract-v1"
    def extract(self, vaers_id, narrative):
        return ExtractionResult(case=ex_case, confidence=0.9), \
            LLMMeta(model="gemini-3-flash", input_tokens=100, output_tokens=60, latency_ms=800)
class FakeCoder:
    name, version, prompt_version = "coding", "coding@0.1.0", "code-v1"
    def code(self, vaers_id, events):
        return CodingOutput(result=coded, confidence=0.92), \
            LLMMeta(model="gemini-3-flash", input_tokens=50, output_tokens=20, latency_ms=300)
class FakeAssessor:
    name, version, prompt_version = "assessment", "assessment@0.1.0", "assess-v1"
    def assess(self, vaers_id, *, extracted, coded=None):
        return AssessmentOutput(seriousness=SeriousnessAssessment(serious=True, criteria_met=["hospitalization"]),
                                causality=CausalityAssessment(method="WHO-UMC", category="probable", rationale="r"),
                                confidence=0.8), \
            LLMMeta(model="gemini-3-pro", input_tokens=80, output_tokens=40, latency_ms=900)
class FakeNarrator:
    name, version, prompt_version = "narrative_qc", "narrative_qc@0.1.0", "narrative-v1"
    def __init__(self, hitl=False): self._hitl = hitl
    def run(self, vaers_id, *, extracted, coded=None, seriousness=None, causality=None):
        return NarrativeQCOutput(narrative="N ...", completeness={"completeness_score": 0.95, "gaps": []},
                                 qc_flags=[], overall_confidence=0.9, hitl_recommended=self._hitl), \
            LLMMeta(model="gemini-3-pro", input_tokens=120, output_tokens=80, latency_ms=1100)
class FakeBQ:
    def __init__(self): self.inserts = []
    def insert_row(self, table, row): self.inserts.append((table, row))

cfg = Settings(project="test", hitl_confidence_threshold=0.75)
bq = FakeBQ()
orch = Orchestrator(cfg, bq, triage=FakeTriage(), extractor=FakeExtractor(), coder=FakeCoder(),
                    assessor=FakeAssessor(), narrator=FakeNarrator(), pipeline_version=PIPELINE_VERSION_PHASE3)
res = orch.run_case("V1", "A 70 yo female had chest pain and was hospitalized after dose.", "01012024")

steps = [r for t, r in bq.inserts if t == "agt_step_event"]
case_row = [r for t, r in bq.inserts if t == "agt_case_output"][0]
run_row = [r for t, r in bq.inserts if t == "agt_run"][0]

check("five step events", len(steps) == 5)
check("seq 1..5 ordered", [s["seq"] for s in steps] == [1, 2, 3, 4, 5])
check("agent order", [s["agent_name"] for s in steps] ==
      ["triage", "extraction", "coding", "assessment", "narrative_qc"])
check("seriousness populated", json.loads(case_row["seriousness"])["serious"] is True)
check("causality populated (WHO-UMC)", json.loads(case_row["causality"])["category"] == "probable")
check("narrative populated", case_row["narrative"] == "N ...")
check("coded_pts present", case_row["coded_pts"] == ["Chest pain"])
check("model_config has all 5 models", len(json.loads(run_row["model_config"])) == 5)
check("overall = min of confidences", abs(case_row["overall_confidence"] - 0.8) < 1e-9)
check("serious surfaced in summary", res["serious"] is True)

# narrative QC can force HITL even when confident
bq2 = FakeBQ()
orch2 = Orchestrator(cfg, bq2, triage=FakeTriage(), extractor=FakeExtractor(), coder=FakeCoder(),
                     assessor=FakeAssessor(), narrator=FakeNarrator(hitl=True),
                     pipeline_version=PIPELINE_VERSION_PHASE3)
r2 = orch2.run_case("V2", "text", None)
check("narrative hitl_recommended forces HITL", r2["hitl_required"] is True)

# orchestrator runs whatever it is given (extractor only)
bq3 = FakeBQ()
orch3 = Orchestrator(cfg, bq3, extractor=FakeExtractor())
r3 = orch3.run_case("V3", "text", None)
check("extractor-only chain: 1 step, no seriousness",
      r3["steps"] == 1 and [r for t, r in bq3.inserts if t == "agt_case_output"][0]["seriousness"] is None)

print(f"\nALL {passed} CHECKS PASSED")
