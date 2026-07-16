"""Typed agent contracts (Pydantic v2).

These models are the single source of truth: the SAME model is passed to
Gemini as `response_schema` (constraining generation) and used to validate
what gets persisted. `model_json_schema()` reproduces the JSON Schema in
agent-contracts.json.

Phase 1 ships the extraction contract + shared structures. Phase 2 adds
CodedEvent / CodingResult / SeriousnessAssessment / CausalityAssessment
(already specified in agent-contracts.json).
"""
from __future__ import annotations
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


class _Strict(BaseModel):
    # Reject unknown fields so a malformed agent response fails fast.
    model_config = ConfigDict(extra="forbid")


class Sex(str, Enum):
    male = "male"
    female = "female"
    unknown = "unknown"


class Outcome(str, Enum):
    recovered = "recovered"
    recovering = "recovering"
    not_recovered = "not_recovered"
    recovered_with_sequelae = "recovered_with_sequelae"
    fatal = "fatal"
    unknown = "unknown"


class ProductRole(str, Enum):
    suspect = "suspect"
    concomitant = "concomitant"


class Product(_Strict):
    name: str = Field(description="Product name exactly as stated")
    manufacturer: Optional[str] = None
    dose_series: Optional[str] = None
    route: Optional[str] = None
    role: ProductRole


class ExtractedEvent(_Strict):
    verbatim: str = Field(description="Adverse event term exactly as written in the narrative")
    onset_date: Optional[str] = Field(default=None, description="ISO 8601 (YYYY-MM-DD); null if not stated")
    outcome: Optional[Outcome] = None


class Patient(_Strict):
    age_years: Optional[float] = None
    sex: Sex


class ExtractedCase(_Strict):
    """Persisted as agt_case_output.extracted"""
    patient: Patient
    products: List[Product] = Field(default_factory=list)
    events: List[ExtractedEvent] = Field(default_factory=list)
    vaccination_date: Optional[str] = Field(default=None, description="ISO 8601; null if not stated")
    onset_date: Optional[str] = Field(default=None, description="ISO 8601; null if not stated")
    days_to_onset: Optional[int] = None
    concomitant_meds: List[str] = Field(default_factory=list)
    medical_history: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)


class ExtractionResult(_Strict):
    """Top-level output of the extraction agent."""
    case: ExtractedCase
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence 0.0-1.0")


# --- Phase 2: coding ---

class CodedEvent(_Strict):
    verbatim: str = Field(description="Event term as written in the narrative")
    meddra_pt: str = Field(description="Assigned MedDRA Preferred Term (from the in-scope PT list)")
    meddra_version: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    requires_review: bool = False


class CodingResult(_Strict):
    """Persisted as agt_case_output.coded_detail."""
    coded: List[CodedEvent] = Field(default_factory=list)
    uncoded: List[str] = Field(default_factory=list, description="Verbatim events with no confident PT match")


class CodingOutput(_Strict):
    """Top-level output of the coding agent."""
    result: CodingResult
    confidence: float = Field(ge=0.0, le=1.0)


# --- Phase 3: triage, assessment, narrative + QC ---

class SeriousnessCriterion(str, Enum):
    death = "death"
    life_threatening = "life_threatening"
    hospitalization = "hospitalization"
    disability = "disability"
    congenital_anomaly = "congenital_anomaly"
    other_medically_important = "other_medically_important"


class ValidityCriterion(str, Enum):
    identifiable_patient = "identifiable_patient"
    identifiable_reporter = "identifiable_reporter"
    suspect_product = "suspect_product"
    adverse_event = "adverse_event"


class TriagePriority(str, Enum):
    expedited = "expedited"
    standard = "standard"
    non_serious = "non_serious"


class SeriousnessScreen(_Strict):
    serious: bool
    criteria_flagged: List[SeriousnessCriterion] = Field(default_factory=list)


class TriageOutput(_Strict):
    valid: bool = Field(description="Meets the 4 minimum ICSR criteria")
    missing_criteria: List[ValidityCriterion] = Field(default_factory=list)
    seriousness_screen: SeriousnessScreen
    priority: TriagePriority
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: Optional[str] = None


class CausalityMethod(str, Enum):
    who_umc = "WHO-UMC"
    naranjo = "Naranjo"


class CausalityCategory(str, Enum):
    certain = "certain"
    probable = "probable"
    possible = "possible"
    unlikely = "unlikely"
    conditional = "conditional"
    unassessable = "unassessable"


class SeriousnessAssessment(_Strict):
    """Persisted as agt_case_output.seriousness."""
    serious: bool
    criteria_met: List[SeriousnessCriterion] = Field(default_factory=list)


class CausalityAssessment(_Strict):
    """Persisted as agt_case_output.causality (shown, not scored)."""
    method: CausalityMethod
    category: CausalityCategory
    score: Optional[float] = None
    rationale: str


class AssessmentOutput(_Strict):
    seriousness: SeriousnessAssessment
    causality: CausalityAssessment
    confidence: float = Field(ge=0.0, le=1.0)


class QCType(str, Enum):
    missing_field = "missing_field"
    inconsistency = "inconsistency"
    temporal_anomaly = "temporal_anomaly"
    low_confidence_coding = "low_confidence_coding"
    unmapped_event = "unmapped_event"


class QCSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


class QCFlag(_Strict):
    type: QCType
    severity: QCSeverity
    detail: Optional[str] = None


class Completeness(_Strict):
    completeness_score: float = Field(ge=0.0, le=1.0)
    gaps: List[str] = Field(default_factory=list)


class NarrativeQCOutput(_Strict):
    narrative: str
    completeness: Completeness
    qc_flags: List[QCFlag] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    hitl_recommended: bool


# --- Phase 4: signal detection ---

class SignalRow(BaseModel):
    # Lenient (not _Strict): rows come from BigQuery; tolerate partial selects.
    model_config = ConfigDict(extra="ignore")
    event_pt: str
    a: int = 0
    b: int = 0
    c: int = 0
    d: int = 0
    n_total: int = 0
    prr: Optional[float] = None
    ror: Optional[float] = None
    signal_flag: bool = False


class GeneratedSQL(_Strict):
    sql: str = Field(description="A single read-only BigQuery SELECT")
    rationale: Optional[str] = None


class SignalNarration(_Strict):
    summary: str
    caveats: List[str] = Field(default_factory=list)


class SignalOutput(_Strict):
    generated_sql: str
    results: List[SignalRow] = Field(default_factory=list)
    summary: str
    caveats: List[str] = Field(default_factory=list)
