"""Grounding for the coding agent.

`Grounder` is the interface: given verbatim event terms, return candidate
MedDRA PTs per term. The default `EmbeddingGrounder` embeds the in-scope PT
list (Vertex embeddings) and does nearest-neighbour retrieval in process -
no extra infra. A `VertexAISearchGrounder` (Discovery Engine) would be the
same interface for production; `NullGrounder` is a no-op for testing / when
running on the model's parametric knowledge alone.
"""

from __future__ import annotations
from typing import Protocol, Dict, List

from .config import Settings


class Grounder(Protocol):
    def ground(self, verbatims: List[str]) -> Dict[str, List[str]]: ...


class NullGrounder:
    def ground(self, verbatims: List[str]) -> Dict[str, List[str]]:
        return {v: [] for v in verbatims}


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


class EmbeddingGrounder:
    """Vertex-embeddings nearest-neighbour retrieval over the PT list."""

    def __init__(self, client, embed_model: str, pt_terms: List[str], top_k: int = 5):
        import numpy as np

        self._client = client
        self._model = embed_model
        self.top_k = top_k
        self.pt_terms = list(pt_terms)
        mat = (
            self._embed(self.pt_terms)
            if self.pt_terms
            else np.zeros((0, 1), dtype="float32")
        )
        # pre-normalize for cosine
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
        self._pt_vecs = (mat / norms).astype("float32")

    def _embed(self, texts: List[str]):
        import numpy as np

        vecs: List[List[float]] = []
        for chunk in _chunks(texts, 250):
            resp = self._client.models.embed_content(model=self._model, contents=chunk)
            vecs.extend(e.values for e in resp.embeddings)
        return np.array(vecs, dtype="float32")

    def ground(self, verbatims: List[str]) -> Dict[str, List[str]]:
        import numpy as np

        if not verbatims or not self.pt_terms:
            return {v: [] for v in verbatims}
        q = self._embed(verbatims)
        q = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-9)
        sims = q @ self._pt_vecs.T  # [n_query, n_pt]
        out: Dict[str, List[str]] = {}
        for i, v in enumerate(verbatims):
            top = np.argsort(-sims[i])[: self.top_k]
            out[v] = [self.pt_terms[j] for j in top]
        return out


def load_pt_terms(cfg: Settings) -> List[str]:
    """Fetch the in-scope MedDRA PT list from ref_meddra_pt."""
    from .clients import BigQuery

    bq = BigQuery(cfg)
    rows = bq.query(
        f"SELECT pt_term FROM `{cfg.ds}.ref_meddra_pt` ORDER BY occurrence_count DESC"
    )
    return [r["pt_term"] for r in rows]


def build_embedding_grounder(cfg: Settings) -> EmbeddingGrounder:
    from .clients import genai_client

    return EmbeddingGrounder(
        genai_client(cfg), cfg.embed_model, load_pt_terms(cfg), cfg.grounding_top_k
    )
