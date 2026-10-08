"""Disease-domain rules for aligning questions with guideline folders.

Basis:
  - Each DiseaseSpec.key must match a folder under
    storage/knowledge_base/documents/<key>/
  - Keywords are conservative disease names or disease-specific aliases.
  - Every matched keyword is written to the processed data for auditing.
  - This is NOT clinical diagnosis coding and NOT a gold label for
    evaluation metrics. It is a dataset-construction filter.

When you add a new guideline disease:
  1. Add PDFs under knowledge_base/documents/<key>/
  2. Append a DiseaseSpec here with Chinese terms that commonly appear
     in patient questions for that disease.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiseaseSpec:
    key: str
    label: str
    keywords: tuple[str, ...]


# Current guideline coverage in this project (3 diseases).
DISEASES: tuple[DiseaseSpec, ...] = (
    DiseaseSpec(
        key="lung_cancer",
        label="肺癌",
        keywords=(
            "肺癌",
            "肺腺癌",
            "肺鳞癌",
        ),
    ),
    DiseaseSpec(
        key="diabetes",
        label="糖尿病",
        keywords=("糖尿病",),
    ),
    DiseaseSpec(
        key="hypertension",
        label="高血压",
        keywords=("高血压",),
    ),
)


@dataclass(frozen=True)
class DiseaseMatch:
    disease: DiseaseSpec
    matched_keywords: tuple[str, ...]


def detect_diseases(text: str) -> tuple[DiseaseMatch, ...]:
    """Return every disease domain matched by explicit disease terms."""
    normalized = (text or "").strip().lower()
    if not normalized:
        return ()
    matches: list[DiseaseMatch] = []
    for disease in DISEASES:
        keywords = tuple(
            keyword for keyword in disease.keywords if keyword.lower() in normalized
        )
        if keywords:
            matches.append(DiseaseMatch(disease=disease, matched_keywords=keywords))
    return tuple(matches)
