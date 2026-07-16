"""Configuration - all settings come from the environment (see .env.example).

No secrets live here; on GCP, auth is via Application Default Credentials.
"""
from __future__ import annotations
import os
from dataclasses import dataclass

# Version stamps written into the audit trail (agt_run / agt_step_event).
PIPELINE_VERSION = "pipeline@0.1.0-phase1"
PIPELINE_VERSION_PHASE2 = "pipeline@0.2.0-phase2"
PIPELINE_VERSION_PHASE3 = "pipeline@0.3.0-phase3"
EXTRACTION_AGENT_VERSION = "extraction@0.1.0"
EXTRACTION_PROMPT_VERSION = "extract-v1"
CODING_AGENT_VERSION = "coding@0.1.0"
CODING_PROMPT_VERSION = "code-v1"
TRIAGE_AGENT_VERSION = "triage@0.1.0"
TRIAGE_PROMPT_VERSION = "triage-v1"
ASSESSMENT_AGENT_VERSION = "assessment@0.1.0"
ASSESSMENT_PROMPT_VERSION = "assess-v1"
NARRATIVE_AGENT_VERSION = "narrative_qc@0.1.0"
NARRATIVE_PROMPT_VERSION = "narrative-v1"
SIGNAL_AGENT_VERSION = "signal@0.1.0"
SIGNAL_PROMPT_VERSION = "signal-v1"


@dataclass(frozen=True)
class Settings:
    project: str
    location: str = "us-central1"
    dataset: str = "pv_vigil"
    bucket: str = ""                       # GCS bucket for raw landing / lineage
    # Confirm the exact model IDs available in your project's Model Garden.
    model_flash: str = "gemini-3-flash"    # high-throughput stages (triage / extraction / coding)
    model_pro: str = "gemini-3-pro"        # reasoning stages (assessment / narrative / signal)
    embed_model: str = "text-embedding-005"  # Vertex embeddings for grounding
    grounding_top_k: int = 5               # candidate PTs retrieved per event
    # Demo scope: a single product family.
    scope_vax_type: str = "COVID19"
    scope_manufacturer: str = ""           # optional further narrowing (blank = all manufacturers)
    # Slice selection.
    min_narrative_chars: int = 200
    live_slice_size: int = 200
    # Routing.
    hitl_confidence_threshold: float = 0.75

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            project = os.environ["VIGIL_PROJECT"]
        except KeyError as e:
            raise RuntimeError("VIGIL_PROJECT must be set (your GCP project id)") from e
        return cls(
            project=project,
            location=os.environ.get("VIGIL_LOCATION", "us-central1"),
            dataset=os.environ.get("VIGIL_DATASET", "pv_vigil"),
            bucket=os.environ.get("VIGIL_BUCKET", ""),
            model_flash=os.environ.get("VIGIL_MODEL_FLASH", "gemini-3-flash"),
            model_pro=os.environ.get("VIGIL_MODEL_PRO", "gemini-3-pro"),
            embed_model=os.environ.get("VIGIL_EMBED_MODEL", "text-embedding-005"),
            grounding_top_k=int(os.environ.get("VIGIL_GROUNDING_TOPK", "5")),
            scope_vax_type=os.environ.get("VIGIL_SCOPE_VAX_TYPE", "COVID19"),
            scope_manufacturer=os.environ.get("VIGIL_SCOPE_MANUFACTURER", ""),
            min_narrative_chars=int(os.environ.get("VIGIL_MIN_NARRATIVE_CHARS", "200")),
            live_slice_size=int(os.environ.get("VIGIL_LIVE_SLICE_SIZE", "200")),
            hitl_confidence_threshold=float(os.environ.get("VIGIL_HITL_THRESHOLD", "0.75")),
        )

    @property
    def ds(self) -> str:
        """Fully-qualified dataset, e.g. my-proj.pv_vigil"""
        return f"{self.project}.{self.dataset}"

    def table(self, name: str) -> str:
        return f"{self.ds}.{name}"
