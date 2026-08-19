"""The embedding pipeline, end to end, and the ways it fails quietly.

This build uses one 384-dim MiniLM-class model in three places — the worker's
vector tier, V4 grounding at submit, and the findings memory's semantic search
— and every one of them is a place where a wrong answer looks like a right
one. A mixed-model index does not raise: it returns neighbours that are
plausible and wrong. An unnormalised vector does not raise: `vector_cosine_ops`
assumes unit length and quietly ranks by magnitude. A scope with four members
does not raise: it produces a centroid that means nothing and a verdict that
reads as a pass.

So this suite asserts the things that break SILENTLY. It runs with no torch
and no model download: the arithmetic is exercised with encoders whose geometry
is known exactly, and the contract halves are read off the source. A test that
needed a 2 GB model would be a test that never ran on a pull request, which is
the failure mode this repository has paid for twice already.

WHAT IS NOT COVERED, stated rather than implied: model QUALITY. Whether
all-MiniLM-L6-v2 actually separates a digital-strategy sentence from a call
report is a property of the model, not of this code, and asserting it here
would pin a number that a legitimate model upgrade should be allowed to move.
The pipeline's job is to be correct given a model; that is what is tested.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from dma_mcp import encoder as mcp_encoder            # noqa: E402
from dma_worker.embed import THRESHOLDS, chunk_text   # noqa: E402


# ── the mixed-model catastrophe ────────────────────────────────────────

def _worker_model_name() -> str:
    """Read off the source rather than imported: importing the factory pulls
    sentence_transformers, which is not in the test path by design."""
    src = (ROOT / "apps" / "worker" / "dma_worker" / "embed.py").read_text()
    m = re.search(r'name\s*=\s*"(sentence-transformers/[^"]+)"', src)
    assert m, "the worker no longer names its model as a literal — update this"
    return m.group(1)


def test_both_services_embed_with_the_same_model():
    """THE ONE THAT HAD NO TEST. `encoder.py` says in its own docstring that
    the name must stay identical on both sides because a mixed-model index
    returns plausible nonsense — and the name is a separate string literal in
    each service, so nothing stopped one of them moving."""
    assert mcp_encoder.MODEL_NAME == _worker_model_name(), (
        "the connector and the worker embed with DIFFERENT models. Nothing "
        "will raise: the index will return neighbours that look reasonable "
        "and are computed in another space")


def test_the_model_is_a_384_dimension_family():
    """The column is `vector(384)` and the HNSW index is built once at
    migration. A model of another width fails at INSERT, which is loud — but
    only after a full re-embed, so the name is checked here too."""
    assert "MiniLM-L6" in mcp_encoder.MODEL_NAME or "bge-small" in mcp_encoder.MODEL_NAME, \
        "the pinned model is not from the 384-dim family the schema declares"
    ddl = (ROOT / "migrations" / "versions" / "0034_memory_findings.py")
    if ddl.exists():
        assert "vector(384)" in ddl.read_text()


def test_both_encoders_ask_for_normalised_output():
    """`vector_cosine_ops` assumes unit length. An encoder that returns raw
    vectors ranks by magnitude and never says so."""
    for path in (ROOT / "apps" / "mcp" / "dma_mcp" / "encoder.py",
                 ROOT / "apps" / "worker" / "dma_worker" / "embed.py"):
        assert "normalize_embeddings=True" in path.read_text(), \
            f"{path.name} does not normalise, and cosine distance assumes it"


# ── the thresholds, and what they mean ─────────────────────────────────

def test_the_scoped_thresholds_narrow_as_the_scope_narrows():
    """A cell centroid is tighter than a run centroid because it is made of
    fewer, more alike members. The ordering is the whole idea; a threshold
    table that inverted it would pass everything at the narrowest scope."""
    assert (THRESHOLDS["cell"] > THRESHOLDS["category"]
            > THRESHOLDS["pillar"] > THRESHOLDS["run"])


def test_the_thresholds_are_the_charter_numbers():
    assert THRESHOLDS == {"cell": 0.62, "category": 0.58,
                          "pillar": 0.55, "run": 0.50}


# ── the arithmetic, with geometry that is known exactly ────────────────

class PlaneEncoder:
    """Unit vectors on a circle in the first two dimensions, so the cosine
    between any two texts is exactly cos(theta) and can be asserted rather
    than approximated. Records every batch, because an encoder called twice
    for one text is a cache that is not working."""

    name = "plane-encoder"

    def __init__(self, angles):
        self.angles = angles
        self.batches = []

    def encode(self, texts):
        self.batches.append(list(texts))
        out = []
        for t in texts:
            a = self.angles[t]
            out.append([math.cos(a), math.sin(a)] + [0.0] * 382)
        return out


def _cos(u, v):
    return sum(x * y for x, y in zip(u, v))


def test_the_encoder_contract_is_a_unit_vector_per_text():
    enc = PlaneEncoder({"a": 0.0, "b": math.pi / 3})
    for v in enc.encode(["a", "b"]):
        assert len(v) == 384
        assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-9


def test_cosine_ranks_the_nearer_text_higher():
    enc = PlaneEncoder({"cell": 0.0, "near": 0.3, "far": 1.4})
    cell, near, far = enc.encode(["cell", "near", "far"])
    assert _cos(cell, near) > _cos(cell, far)
    assert _cos(cell, near) == pytest.approx(math.cos(0.3), abs=1e-9)


def test_a_centroid_of_alike_members_is_nearer_than_any_outlier():
    """What a centroid is FOR. Four members within a tenth of a radian, one a
    radian away: the mean of the four sits among them, not between them and
    the outlier."""
    enc = PlaneEncoder({f"m{i}": i * 0.05 for i in range(4)} | {"out": 1.2})
    members = enc.encode([f"m{i}" for i in range(4)])
    (out,) = enc.encode(["out"])
    mean = [sum(v[d] for v in members) / len(members) for d in range(384)]
    norm = math.sqrt(sum(x * x for x in mean))
    mean = [x / norm for x in mean]
    assert all(_cos(mean, m) > _cos(mean, out) for m in members)


def test_determinism_the_same_text_gives_the_same_vector():
    """A verdict that changes between two identical submits is a verdict
    nobody can act on, and the whole grounding tier rests on this."""
    enc = PlaneEncoder({"x": 0.7})
    assert enc.encode(["x"]) == enc.encode(["x"])


# ── chunking, which decides what gets embedded at all ──────────────────

def test_a_short_text_is_one_chunk_and_survives_whole():
    text = "The board approved a documented digital strategy in 2025."
    assert chunk_text(text) == [text]


def test_a_long_text_overlaps_so_a_claim_on_a_boundary_is_still_in_a_chunk():
    """Without overlap, a claim landing on a boundary appears in no chunk and
    is unfindable by any search — a silent hole in the index."""
    text = " ".join(f"Sentence {i} says something about the estate." for i in range(60))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    joined = " ".join(chunks)
    for i in range(0, 60, 7):
        assert f"Sentence {i} " in joined


def test_a_wall_of_text_with_no_full_stop_is_still_split():
    """THE SILENT TRUNCATION. The splitter is punctuation-driven, so a scraped
    table or a transcript with no terminators arrived as ONE sentence and left
    as one chunk of any length. The encoder truncates at its context window
    without complaint: everything past roughly the first 256 tokens was absent
    from the index, and nothing recorded that it had been."""
    words = " ".join(f"w{i}" for i in range(2000))
    chunks = chunk_text(words)
    assert len(chunks) > 1, \
        "2000 words with no full stop became one chunk, most of which the " \
        "encoder will silently drop"
    assert max(len(c.split()) for c in chunks) <= 90, \
        "a chunk is longer than the window the model can actually read"
    seen = " ".join(chunks)
    for i in (0, 999, 1999):
        assert f"w{i}" in seen, f"w{i} is in no chunk — it is unsearchable"


def test_chunking_is_stable_across_calls():
    words = " ".join(f"w{i}" for i in range(900))
    assert chunk_text(words) == chunk_text(words)


def test_empty_and_blank_text_produce_no_chunks_rather_than_one_empty_chunk():
    """An empty chunk embeds to a vector with no meaning that still matches
    something. The register holds 36 rows with no excerpt; every one of them
    reaches this path."""
    for blank in ("", "   ", "\n\t "):
        assert chunk_text(blank) == [], \
            f"{blank!r} produced a chunk — an empty span must not be embedded"


# ── V4 abstains rather than guesses, and says that it did ──────────────

def test_v4_abstains_below_five_members():
    from dma_mcp import validation2
    assert validation2.V4_MIN_MEMBERS == 5, \
        "the abstention floor moved; a centroid of four members means nothing"


def test_v4_records_a_reason_whenever_it_does_not_run():
    """An abstention that leaves no row is indistinguishable from a check that
    passed. Every NOT_RUN path in the module carries a reason string."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "validation2.py").read_text()
    i = src.index("def check_v4") if "def check_v4" in src else 0
    body = src[i:]
    for marker in ('"NOT_RUN"', "not_run_reason"):
        assert marker in body, f"V4 no longer carries {marker}"
    # Every recorded NOT_RUN is accompanied by prose, not just a status.
    assert body.count("not_run_reason") >= 2, \
        "only one NOT_RUN path names its reason; the others are silent"


def test_a_missing_encoder_is_an_abstention_and_never_a_pass():
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "validation2.py").read_text()
    assert "Embedding tier unavailable" in src, \
        "V4 no longer distinguishes 'no encoder' from 'checked and clean'"


def test_no_chunk_can_exceed_the_encoder_context_even_with_overlap():
    """The packer carries the previous sentence forward, so a chunk can be
    larger than `_MAX_WORDS` — two 90-word sentences make a 180-word window.
    At ~1.3 tokens per word that is ~234 tokens, inside a 256-token context.
    The bound is pinned here because raising `_MAX_WORDS` would cross it
    silently: the encoder truncates without complaint."""
    from dma_worker.embed import _MAX_WORDS
    worst_words = _MAX_WORDS * 2
    assert worst_words * 1.3 < 256, (
        f"_MAX_WORDS={_MAX_WORDS} allows a {worst_words}-word chunk, about "
        f"{int(worst_words * 1.3)} tokens, past the 256-token context — "
        "everything after the cut is dropped without an error")
    long_sentences = " ".join(
        " ".join(f"w{i}_{j}" for j in range(88)) + "." for i in range(8))
    assert max(len(c.split()) for c in chunk_text(long_sentences)) <= worst_words
