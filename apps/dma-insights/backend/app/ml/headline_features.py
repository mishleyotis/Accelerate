"""Shape features for the headline gate — importable at unpickle time.

Lives outside the trainer so joblib artifacts reference a stable module path
(a function defined in a ``python -m`` entrypoint pickles as ``__main__`` and
can never be loaded by the serving wrapper).
"""
from __future__ import annotations

import re

import numpy as np

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_EID_RE = re.compile(r"\bE-\d{1,4}\b")


def numeric_features(texts) -> np.ndarray:
    rows = []
    for t in texts:
        t = t or ""
        sents = [x for x in _SENT_RE.split(t.strip()) if len(x.strip()) > 3]
        rows.append([
            min(len(t) / 400.0, 2.0),
            min(len(sents) / 4.0, 2.0),
            min(len(_EID_RE.findall(t)) / 2.0, 2.0),
            1.0 if any(ch.isdigit() for ch in t) else 0.0,
        ])
    return np.asarray(rows)
