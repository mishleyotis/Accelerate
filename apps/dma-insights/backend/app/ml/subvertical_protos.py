"""Zero-shot class-prototype features for the subvertical classifier.

Each subvertical gets a natural-language prototype; an entity's feature is
its semantic relevance to each prototype (MiniLM when baked, lexical
fallback otherwise). Classes starved of training rows (FC, CIB, NON_FI)
get discriminative signal the supervised features cannot supply. Lives in
a stable module path so joblib artifacts unpickle outside the trainer.
"""
from __future__ import annotations

import numpy as np

CLASS_PROTOTYPES: dict[str, str] = {
    "AM": "asset management firm managing investment funds with assets under "
          "management, fund administration, custody and institutional clients",
    "CIB": "payments infrastructure and interbank clearing and settlement "
           "system operator, corporate and institutional banking rails",
    "CL": "commercial lender providing business loans, equipment finance and "
          "commercial credit outside a bank charter",
    "CU": "member-owned credit union regulated by the NCUA serving members "
          "with share accounts and consumer lending",
    "FC": "farm credit association under the Farm Credit Administration "
          "providing agricultural loans to farmers, ranchers and rural "
          "cooperatives",
    "IB": "insurance broker or brokerage placing policies for clients and "
          "earning placement commissions across carriers",
    "IC": "insurance carrier underwriting policies, paying claims and "
          "managing policyholder surplus and combined ratio",
    "NON_FI": "software or technology company, not a financial institution, "
              "selling SaaS products or business services",
    "RB": "chartered bank with branches, deposits and consumer and "
          "commercial banking regulated by the FDIC or OCC",
    "RIA": "registered investment adviser or wealth management firm giving "
           "financial planning and advisory services to clients",
}

_CLASSES = sorted(CLASS_PROTOTYPES)
_index = None


def _get_index():
    global _index
    if _index is None:
        from app.services.nlp.semantic import SemanticIndex
        idx = SemanticIndex()
        idx.fit([(c, CLASS_PROTOTYPES[c]) for c in _CLASSES])
        _index = idx
    return _index


def prototype_features(texts) -> np.ndarray:
    """Relevance of each text to each class prototype, [n, 10]."""
    idx = _get_index()
    rows = []
    for t in texts:
        scores = dict.fromkeys(_CLASSES, 0.0)
        for cls, score in idx.top_k((t or "")[:2000], k=len(_CLASSES),
                                    min_score=-1.0):
            scores[cls] = float(score)
        rows.append([scores[c] for c in _CLASSES])
    return np.asarray(rows)
