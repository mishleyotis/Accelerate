"""Shared NLP platform — the single substrate every derive/parse script uses.

Why this package exists: the 2026-06 QA audits traced most data-quality
defects (defaulted timeline dates, garbage titles, negation misses,
template prose, spurious year-series, verbatim tech-stack noise) to
per-script ad-hoc regex. The remediation plan (Part 2) mandates ONE
report-agnostic toolkit under ``app/services/nlp/`` so every script
shares the same segmentation, NER, date resolution, quantity extraction,
causal decomposition, polarity, similarity, taxonomy, title generation,
quote mining, pattern registry, and quality rubric.

Degradation contract: spaCy (``en_core_web_sm``) is loaded lazily and at
most once via :func:`get_nlp`. When the model cannot load (image built
without the ``nlp`` extra, model wheel missing), the module flag
``NLP_DEGRADED`` flips to True and every function in the package falls
back to its deterministic regex tier — the toolkit NEVER raises because
of a missing model, so the ingest/derive chain cannot crash on it.
Callers stamp ``nlp_degraded=true`` into job_executions when the flag is
set.
"""
from __future__ import annotations

from typing import Any

NLP_DEGRADED: bool = False

_NLP: Any = None
_LOAD_ATTEMPTED: bool = False


def get_nlp() -> Any:
    """The lazy spaCy singleton — ``en_core_web_sm`` loaded once, or None.

    Never raises: on any load failure the package-level ``NLP_DEGRADED``
    flag is set and None is returned, which every submodule treats as
    "use the regex tier". Subsequent calls are cheap (no re-attempt —
    a broken model install will not slow down a 94-client derive pass
    with repeated import attempts).
    """
    global _NLP, _LOAD_ATTEMPTED, NLP_DEGRADED
    if _LOAD_ATTEMPTED:
        return _NLP
    _LOAD_ATTEMPTED = True
    try:
        # Deferred import — core installs (no `nlp` extra) never pay for it.
        import spacy

        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        _NLP = None
        NLP_DEGRADED = True
    return _NLP


def is_degraded() -> bool:
    """True when the spaCy tier is unavailable (checked AFTER a load attempt).

    Reads the flag through the module so callers that did
    ``from app.services.nlp import NLP_DEGRADED`` at import time (before
    the first :func:`get_nlp` call) are not misled by a stale binding.
    """
    return NLP_DEGRADED


# Submodule functions re-exported at package level so call sites can do
# ``from app.services.nlp import sentences, resolve_event_date, ...``.
# These imports MUST come after get_nlp() is defined: submodules resolve
# the singleton through the package at call time.
from app.services.nlp.causal import decompose  # noqa: E402
from app.services.nlp.dates import extract_windows, resolve_event_date  # noqa: E402
from app.services.nlp.entities import extract  # noqa: E402
from app.services.nlp.patterns import (  # noqa: E402
    match_artifact,
    record_pattern_gap,
    register,
)
from app.services.nlp.polarity import is_event, is_negated_absence, signal  # noqa: E402
from app.services.nlp.quality import markdown_lint, rubric_score  # noqa: E402
from app.services.nlp.quantities import extract_metrics, extract_year_series  # noqa: E402
from app.services.nlp.quotes import mine_quotes  # noqa: E402
from app.services.nlp.segment import clauses, clip_sentences, sentences  # noqa: E402
from app.services.nlp.similarity import LexicalIndex, near_duplicates  # noqa: E402
from app.services.nlp.taxonomy import classify, split_cell  # noqa: E402
from app.services.nlp.titlecraft import make_title  # noqa: E402


class NlpToolkit:
    """Facade bundling every toolkit function behind one object.

    Scripts that want dependency injection (or a single import) grab an
    ``NlpToolkit()`` instead of ten module imports; the methods are the
    exact module functions, so behaviour (including regex degradation)
    is identical either way.
    """

    # segmentation
    sentences = staticmethod(sentences)
    clip_sentences = staticmethod(clip_sentences)
    clauses = staticmethod(clauses)
    # entities / dates / quantities
    extract_entities = staticmethod(extract)
    resolve_event_date = staticmethod(resolve_event_date)
    extract_windows = staticmethod(extract_windows)
    extract_metrics = staticmethod(extract_metrics)
    extract_year_series = staticmethod(extract_year_series)
    # discourse / polarity
    decompose = staticmethod(decompose)
    is_negated_absence = staticmethod(is_negated_absence)
    signal = staticmethod(signal)
    is_event = staticmethod(is_event)
    # similarity / taxonomy / titles / quotes
    near_duplicates = staticmethod(near_duplicates)
    classify = staticmethod(classify)
    split_cell = staticmethod(split_cell)
    make_title = staticmethod(make_title)
    mine_quotes = staticmethod(mine_quotes)
    # pattern registry / quality
    register_pattern = staticmethod(register)
    match_artifact = staticmethod(match_artifact)
    record_pattern_gap = staticmethod(record_pattern_gap)
    rubric_score = staticmethod(rubric_score)
    markdown_lint = staticmethod(markdown_lint)

    LexicalIndex = LexicalIndex

    @property
    def degraded(self) -> bool:
        return is_degraded()


__all__ = [
    "NLP_DEGRADED",
    "LexicalIndex",
    "NlpToolkit",
    "clauses",
    "classify",
    "clip_sentences",
    "decompose",
    "extract",
    "extract_metrics",
    "extract_windows",
    "extract_year_series",
    "get_nlp",
    "is_degraded",
    "is_event",
    "is_negated_absence",
    "make_title",
    "markdown_lint",
    "match_artifact",
    "mine_quotes",
    "near_duplicates",
    "record_pattern_gap",
    "register",
    "resolve_event_date",
    "rubric_score",
    "sentences",
    "signal",
    "split_cell",
]
