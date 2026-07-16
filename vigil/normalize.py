"""Pure helpers for normalization and ground-truth matching.

Kept free of any cloud imports so the matching rules can be unit-tested
locally and reused by both the pipeline and the SQL eval (which mirrors
the same logic in BigQuery).
"""

from __future__ import annotations
import re
from typing import Optional, List


def normalize_sex(value: Optional[str]) -> str:
    if not value:
        return "unknown"
    v = value.strip().lower()
    if v in ("m", "male"):
        return "male"
    if v in ("f", "female"):
        return "female"
    return "unknown"


def sex_match(extracted_sex: Optional[str], gt_sex_raw: Optional[str]) -> bool:
    return normalize_sex(extracted_sex) == normalize_sex(gt_sex_raw)


def age_match(
    extracted_age: Optional[float], gt_age: Optional[float], tol: float = 1.0
) -> Optional[bool]:
    if extracted_age is None or gt_age is None:
        return None  # not scorable
    return abs(float(extracted_age) - float(gt_age)) <= tol


def normalize_product(name: Optional[str]) -> str:
    if not name:
        return ""
    # Lowercase, collapse any run of non-alphanumerics to a single space.
    s = re.sub(r"[^a-z0-9]+", " ", name.lower())
    return re.sub(r"\s+", " ", s).strip().upper()


def product_recall(
    extracted_products: List[str], gt_products: List[str]
) -> Optional[float]:
    """Fraction of ground-truth products whose normalized name is a
    substring-of/equal-to some extracted product (loose name match)."""
    gt = [normalize_product(p) for p in gt_products if p]
    if not gt:
        return None
    ext = [normalize_product(p) for p in extracted_products if p]
    hit = 0
    for g in gt:
        if any(g == e or g in e or e in g for e in ext):
            hit += 1
    return hit / len(gt)


def normalize_pt(term):
    """Normalize a MedDRA PT for set comparison (mirrors the SQL UPPER(TRIM(...)))."""
    if not term:
        return ""
    return re.sub(r"\s+", " ", str(term).strip().upper())


def coding_prf(predicted, gold):
    """Precision/recall/F1 between predicted and gold MedDRA PT sets.

    Mirrors vw_eval_case in BigQuery (set-based, normalized terms). Returns
    None for precision/recall/f1 when undefined (empty denominators).
    """
    P = {normalize_pt(x) for x in predicted if x}
    G = {normalize_pt(x) for x in gold if x}
    tp = len(P & G)
    fp = len(P - G)
    fn = len(G - P)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * tp) / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }
