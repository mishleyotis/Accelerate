"""Stage 1.4 — the vector tier's ingest half (TRD §18).

At ingest the bundle is chunked, embedded and centroided; the connector's
V4 check at submit probes what this module wrote. The serving path never
touches any of it.

Membership per scope (TRD §18 "Centroids are scoped, not global"):
  cell      evidence linked to that sub-capability (+ its score rationale)
  category  all cells in the category, plus report text tagged to it
  pillar    all categories in the pillar, plus the pillar deep-dive
  run       everything in the bundle

Rows are stored at EVERY scope they are a member of — the attribution
query filters on scope_kind, so a pillar-scope probe needs pillar-scope
rows. Centroids are the mean of the L2-normalised members, renormalised;
member_n is written even below five, where the submit-side check
abstains to a recorded NOT_RUN rather than failing closed.

The encoder is injected (``.name``, ``.encode(list[str]) -> list of
384-float lists, L2-normalised``) so the pipeline is testable without
the model; the real MiniLM wrapper lives in minilm_encoder().
"""
from __future__ import annotations

import re
from dataclasses import dataclass

THRESHOLDS = {"cell": 0.62, "category": 0.58, "pillar": 0.55, "run": 0.50}

# Sentence-window chunking, 60-120 tokens, 20% overlap. Tokens are
# approximated by whitespace words (a 384-dim MiniLM tokeniser averages
# ~1.3 tokens/word on this corpus; 50-90 words sits inside the band).
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“(])")
_MAX_WORDS = 90
_MIN_WORDS = 45
_OVERLAP = 0.2

_CATEGORY_TOKEN = re.compile(r"\bP([1-4])C(\d+)\b")
_PILLAR_TOKEN = re.compile(r"\(P([1-4])\)")


def chunk_text(text: str) -> list:
    """Split into sentence windows of ~45-90 words with 20% overlap.
    Deterministic and pure; short texts (an evidence excerpt) pass
    through as a single chunk."""
    words_of = str.split
    sentences = [s.strip() for s in _SENT.split(text.strip()) if s.strip()]
    if not sentences:
        return []
    # A "SENTENCE" LONGER THAN THE WINDOW, split on words rather than carried
    # whole. The splitter is punctuation-driven, so a wall of text with no
    # terminator — a scraped table, a transcript with no full stops, an
    # excerpt whose punctuation the parser lost — arrived here as ONE
    # sentence and left as one chunk of any length. The encoder truncates at
    # its context window without complaint, so everything past the first ~256
    # tokens was absent from the index and nothing recorded that it had been:
    # searchable text silently becoming unsearchable text.
    split = []
    for s in sentences:
        w = words_of(s)
        if len(w) <= _MAX_WORDS:
            split.append(s)
            continue
        # HALF a window per piece, not a whole one. The packer below carries
        # the previous sentence forward as overlap, so whole-window pieces
        # produced 180-word chunks — twice what the encoder reads, which is
        # the same silent truncation in a new place. At half a window a piece
        # plus its carried predecessor is exactly one window.
        piece_n = max(1, _MAX_WORDS // 2)
        for i in range(0, len(w), piece_n):
            split.append(" ".join(w[i:i + piece_n]))
    sentences = split
    chunks, window, count = [], [], 0
    for s in sentences:
        n = len(words_of(s))
        if window and count + n > _MAX_WORDS:
            chunks.append(" ".join(window))
            # carry the tail of the window forward as overlap
            keep, kept = [], 0
            for prev in reversed(window):
                kept += len(words_of(prev))
                keep.insert(0, prev)
                if kept >= _OVERLAP * count:
                    break
            window, count = keep, kept
        window.append(s)
        count += n
    if window:
        tail = " ".join(window)
        if chunks and count < _MIN_WORDS:
            chunks[-1] = chunks[-1] + " " + tail
        else:
            chunks.append(tail)
    return chunks


def _vec_literal(v) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


@dataclass
class _Item:
    source_kind: str    # evidence · report_section · score_rationale
    source_ref: str
    text: str
    scopes: set         # {(scope_kind, scope_id-or-None)}


def _grain_scopes(subcap_ids) -> set:
    scopes = set()
    for sid in subcap_ids:
        parts = sid.split(".")
        category = parts[0]
        pillar = category.split("C")[0]
        scopes.update({("cell", sid), ("category", category), ("pillar", pillar)})
    scopes.add(("run", None))
    return scopes


def collect_items(conn, run_id, rationales: dict | None = None) -> list:
    """Assemble the bundle from the ingested tier (evidence and report
    sections read back post-dedup) plus the parse-time rationales the
    schema deliberately does not store."""
    cur = conn.cursor()
    items = []

    cur.execute(
        """SELECT e.e_id, e.excerpt, array_agg(l.subcap_id)
             FROM evidence_index e
             JOIN evidence_subcap_links l ON l.e_id = e.e_id
            WHERE l.run_id = %s AND e.excerpt IS NOT NULL
            GROUP BY e.e_id, e.excerpt""", (run_id,))
    for e_id, excerpt, subcaps in cur.fetchall():
        items.append(_Item("evidence", e_id, excerpt, _grain_scopes(subcaps)))

    cur.execute(
        """SELECT id, section_kind, pillar_id, heading, body
             FROM document_sections WHERE run_id = %s""", (run_id,))
    for sec_id, kind, pillar_id, heading, body in cur.fetchall():
        scopes = {("run", None)}
        if pillar_id:
            scopes.add(("pillar", pillar_id))
        for m in _PILLAR_TOKEN.finditer(heading or ""):
            scopes.add(("pillar", f"P{m.group(1)}"))
        for m in _CATEGORY_TOKEN.finditer(heading or ""):
            scopes.add(("category", m.group(0)))
        items.append(_Item("report_section", f"section:{sec_id}",
                           f"{heading}\n{body}", scopes))

    for sid, text in (rationales or {}).items():
        if text:
            items.append(_Item("score_rationale", f"rationale:{sid}", text,
                               _grain_scopes([sid])))
    return items


def embed_run(conn, run_id, encoder, rationales: dict | None = None) -> dict:
    """Chunk, embed and centroid one run's bundle. Idempotent: an existing
    embedding set for the run (same model) is replaced wholesale — partial
    indexes are worse than recomputed ones."""
    items = collect_items(conn, run_id, rationales)
    rows = []       # (scope_kind, scope_id, source_kind, source_ref, idx, text)
    for it in items:
        for idx, chunk in enumerate(chunk_text(it.text)):
            for scope_kind, scope_id in sorted(it.scopes, key=str):
                rows.append((scope_kind, scope_id, it.source_kind,
                             it.source_ref, idx, chunk))
    if not rows:
        return {"embeddings": 0, "centroids": 0}

    # one encode per distinct chunk; scope fan-out reuses the vector
    distinct = sorted({r[5] for r in rows})
    vectors = dict(zip(distinct, encoder.encode(distinct)))

    cur = conn.cursor()
    cur.execute("DELETE FROM bundle_centroids WHERE run_id = %s", (run_id,))
    cur.execute("DELETE FROM bundle_embeddings WHERE run_id = %s", (run_id,))
    sums: dict = {}     # (scope_kind, scope_id) -> [count, running sum]
    for scope_kind, scope_id, source_kind, source_ref, idx, chunk in rows:
        v = vectors[chunk]
        cur.execute(
            """INSERT INTO bundle_embeddings
                 (run_id, scope_kind, scope_id, source_kind, source_ref,
                  chunk_index, content, embedding, embedding_model, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())""",
            (run_id, scope_kind, scope_id, source_kind, source_ref,
             idx, chunk, _vec_literal(v), encoder.name))
        key = (scope_kind, scope_id or "")
        acc = sums.setdefault(key, [0, [0.0] * len(v)])
        acc[0] += 1
        acc[1] = [a + b for a, b in zip(acc[1], v)]

    for (scope_kind, scope_id), (n, total) in sums.items():
        mean = [x / n for x in total]
        norm = sum(x * x for x in mean) ** 0.5
        centroid = [x / norm for x in mean] if norm else mean
        cur.execute(
            """INSERT INTO bundle_centroids
                 (run_id, scope_kind, scope_id, centroid, member_n, threshold)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (run_id, scope_kind, scope_id, _vec_literal(centroid), n,
             THRESHOLDS[scope_kind]))
    conn.commit()
    return {"embeddings": len(rows), "centroids": len(sums)}


def minilm_encoder(model_dir: str | None = None):
    """The real 384-dim encoder, loaded lazily so tests never import
    torch. In the worker image the model is bundled at model_dir; local
    dev resolves through the standard cache."""
    from sentence_transformers import SentenceTransformer
    name = "sentence-transformers/all-MiniLM-L6-v2"
    model = SentenceTransformer(model_dir or name, device="cpu")

    class _Encoder:
        def __init__(self):
            self.name = name

        def encode(self, texts):
            return model.encode(texts, normalize_embeddings=True,
                                show_progress_bar=False).tolist()

    return _Encoder()
