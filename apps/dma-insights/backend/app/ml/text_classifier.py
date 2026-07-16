"""Lazy, dependency-optional loader for the trained sklearn text classifiers.

Contract (the no-regression / no-empty-state guarantee):
  * If joblib/sklearn are NOT installed, or the artifact is missing/corrupt, or
    the prediction is below the confidence floor → ``predict`` returns
    ``(None, 0.0)`` and the caller keeps its existing regex/heuristic result.
  * The model is loaded ONCE (module cache) and never trains at runtime.

This is why adding the classifiers is safe on the current runtime image (which
does not yet ship sklearn): every call site degrades to its prior behaviour when
the model can't load. Ship sklearn in the image to activate the models.
"""
from __future__ import annotations

import json
from pathlib import Path

_MODELS_DIR = Path(__file__).resolve().parent / "models"
_CACHE: dict[str, LabelClassifier] = {}


class LabelClassifier:
    """Wraps one committed ``<name>_<version>.joblib`` sklearn pipeline."""

    def __init__(self, name: str, version: str = "v1", min_confidence: float = 0.40):
        self.name = name
        self.version = version
        self.min_confidence = min_confidence
        self._pipe = None
        self._loaded = False
        self._available = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            import joblib
            path = _MODELS_DIR / f"{self.name}_{self.version}.joblib"
            meta_path = path.with_suffix(".meta.json")
            if not path.exists():
                return
            # Version guard: meta must match the requested version.
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("version") != self.version:
                    return
            self._pipe = joblib.load(path)
            self._available = True
        except Exception:
            # Any failure (missing sklearn/joblib, corrupt artifact, version
            # skew) → model unavailable; caller falls back. Never raises.
            self._pipe = None
            self._available = False

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return self._available

    def predict(self, text: str) -> tuple[str | None, float]:
        """Return (label, confidence) or (None, 0.0) when unavailable / low-conf /
        empty input."""
        self._ensure_loaded()
        if not self._available or not text or not text.strip():
            return None, 0.0
        try:
            if hasattr(self._pipe, "predict_proba"):
                proba = self._pipe.predict_proba([text])[0]
                classes = self._pipe.classes_
                best_i = int(proba.argmax())
                conf = float(proba[best_i])
                if conf < self.min_confidence:
                    return None, conf
                return str(classes[best_i]), conf
            # No proba (e.g. LinearSVC) → hard prediction, unknown confidence.
            return str(self._pipe.predict([text])[0]), 1.0
        except Exception:
            return None, 0.0


def get_classifier(name: str, version: str = "v1", min_confidence: float = 0.40) -> LabelClassifier:
    key = f"{name}:{version}:{min_confidence}"
    clf = _CACHE.get(key)
    if clf is None:
        clf = LabelClassifier(name, version, min_confidence)
        _CACHE[key] = clf
    return clf
