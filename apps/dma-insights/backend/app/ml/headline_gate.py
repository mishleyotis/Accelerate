"""Headline/So-What quality gate — serving wrapper (Training Spec Tab 01 §2.2).

``gate_headline(text, surface)`` returns the pre-ship verdict for a headline
or So-What. The deterministic regex rules (vendor-first, threat-tone,
template) are authoritative for the boolean flags and act as a hard gate; the
trained model refines the gold probability. Fail-closed: with no artifact on
disk the wrapper degrades to the rules plus a one-liner heuristic — a
rejected headline is never shipped silently either way.
"""
from __future__ import annotations

import functools
import os
import re
from typing import Any

from app.ml.gold.build_headline_gold import threat_tone, vendor_first
from app.scripts.countercheck_pack import TEMPLATE_RES, _sentence_count

_MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")
_EID_RE = re.compile(r"\bE-\d{1,4}\b")


@functools.lru_cache(maxsize=1)
def load_gate() -> dict[str, Any] | None:
    path = os.path.join(_MODELS_DIR, "headline_gate_v1.joblib")
    try:
        import joblib
        gate = joblib.load(path)
        return gate if isinstance(gate, dict) and "gold_reject" in gate else None
    except Exception:
        return None


def gate_headline(text: str | None, surface: str = "so_what") -> dict:
    t = (text or "").strip()
    if not t:
        return {"verdict": "reject", "p_gold": 0.0,
                "vendor_first": False, "threat_tone": False}
    vf = vendor_first(t)
    tt = threat_tone(t)
    template = any(rx.search(t) for rx in TEMPLATE_RES)
    gate = load_gate()
    if gate is not None:
        conditioned = f"[{surface}] {t}"
        p_gold = float(gate["gold_reject"].predict_proba([conditioned])[0][1])
    else:
        one_liner = (surface == "so_what" and _sentence_count(t) < 2
                     and len(t) < 120)
        p_gold = 0.0 if (vf or tt or template or one_liner) else 0.5
    verdict = "gold" if (p_gold >= 0.5 and not (vf or tt or template)) else "reject"
    return {"verdict": verdict, "p_gold": round(p_gold, 4),
            "vendor_first": vf, "threat_tone": tt}
