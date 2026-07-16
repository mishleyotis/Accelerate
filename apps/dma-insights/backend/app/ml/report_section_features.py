"""Engineered features for the report-section heading classifier.

The 3-fold CV error set is dominated by pillar-number confusions:
headings like "P3 Capability Scorecard" / "P2 — Why It Matters" share
their entire suffix across all four pillar classes, so TF-IDF drowns
the one decisive token. These features surface that token explicitly.
Lives in a stable module path so the joblib pipeline unpickles outside
the trainer (the ``__main__``-pickle failure class).
"""
from __future__ import annotations

import re

import numpy as np

_PILLAR_RE = re.compile(r"\bP(?:illar\s*)?([1-4])\b", re.I)
# Scale chosen so one engineered hit is comparable to a handful of
# TF-IDF n-gram hits under the LR's L2 geometry.
_SCALE = 3.0


def pillar_features(texts) -> np.ndarray:
    """[n, 4] one-hot of the first pillar number named in each heading."""
    out = np.zeros((len(texts), 4))
    for i, t in enumerate(texts):
        m = _PILLAR_RE.search(str(t or ""))
        if m:
            out[i, int(m.group(1)) - 1] = _SCALE
    return out
