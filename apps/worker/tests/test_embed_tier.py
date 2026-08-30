"""Stage 1.4 QA bullets — the vector tier's ingest half.

The encoder is a deterministic stub (no torch in the test path): each
text hashes to a stable unit vector, so scope fan-out, centroid
arithmetic and idempotency are checked exactly. Model quality is not
under test here — only the plumbing the V4 check will stand on.
"""
import hashlib
import math
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_worker.embed import THRESHOLDS, chunk_text, embed_run
from dma_worker.persist import persist_package
from dma_worker.report_parser import ReportSection
from dma_worker.workbook_parser import ParsedScore, WorkbookParse

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"


class StubEncoder:
    name = "stub-encoder-384"

    def encode(self, texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            raw = [(h[i % 32] + i) % 97 - 48 for i in range(384)]
            norm = math.sqrt(sum(x * x for x in raw)) or 1.0
            out.append([x / norm for x in raw])
        return out


# ── chunking is pure and deterministic ─────────────────────────────────
def test_short_text_is_one_chunk_and_long_text_overlaps():
    assert chunk_text("One short excerpt about a bank.") == \
        ["One short excerpt about a bank."]
    sentences = " ".join(
        f"Sentence number {i} carries exactly eight words here." for i in range(40))
    chunks = chunk_text(sentences)
    assert len(chunks) > 1
    assert all(len(c.split()) <= 120 for c in chunks)
    # consecutive chunks share sentences (the 20% overlap)
    for a, b in zip(chunks, chunks[1:]):
        assert a.split(".")[-2].strip() in b


def test_chunking_is_stable():
    text = " ".join(f"Claim {i} is supported by filing {i}." for i in range(60))
    assert chunk_text(text) == chunk_text(text)


# ── the DB half ────────────────────────────────────────────────────────
def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def seeded_run():
    try:
        worker = _connect("dmai-worker@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")

    def clean():
        cur = admin.cursor()
        cur.execute("SELECT id FROM entities WHERE display_id = 'synthetic-embed-bank'")
        for (eid,) in cur.fetchall():
            for sql in (
                "DELETE FROM bundle_centroids WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM bundle_embeddings WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM evidence_subcap_links WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM document_sections WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM parser_observations WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM subcap_scores WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM run_manifest WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                "DELETE FROM runs WHERE entity_id = %s",
                "DELETE FROM evidence_index WHERE entity_id = %s",
                "DELETE FROM entities WHERE id = %s",
            ):
                cur.execute(sql, (eid,))
        admin.commit()

    clean()
    manifest = {"run_id": "DMA-ASM-SEB-20260801-01",
                "institution": {"name": "Synthetic Embed Bank"},
                "versions": {"taxonomy": "v7.0"},
                "assessment": {"date": "2026-08-01"},
                "scores": {"overall": 2.0}}
    wb = WorkbookParse(
        scores=[ParsedScore(subcap_id="P1C1.1.1", pillar_id="P1", category_id="P1C1",
                            capability_id="P1C1.1", name=None, tier=None,
                            score=Decimal("2.0"), source_cell="P1!D2",
                            evidence_quality=None, evidence_refs=["E-001"],
                            rationale="E-001 confirms a documented strategy exists.")],
        observations=[], toggled_out=[], scored_cells=1)
    evidence = [{"e_id": "E-001", "source_name": "AR", "source_url": "https://x.example/a",
                 "excerpt": "The annual report describes a board-approved digital strategy.",
                 "tier": None, "ers": None, "published_date": "2025-12-31",
                 "subcaps": ["P1C1.1.1"]}]
    sections = [ReportSection("pillar_deep_dive", "P1",
                              "Pillar 1: Strategy (P1) — Score 2.0",
                              "The pillar shows early-stage strategy work."),
                ReportSection("executive_summary", None, "SCQA Context",
                              "Situation: a bank with early digital maturity.")]
    res = persist_package(worker, manifest=manifest, workbook=wb,
                          source_folder_id="synthetic", evidence=evidence,
                          sections=sections)
    yield worker, res, {"P1C1.1.1": wb.scores[0].rationale}
    worker.rollback()
    clean()
    worker.close()
    admin.close()


def test_scope_fanout_centroids_and_idempotency(seeded_run):
    worker, res, rationales = seeded_run
    stats = embed_run(worker, res.run_id, StubEncoder(), rationales)
    cur = worker.cursor()

    # evidence + rationale rows exist at cell, category, pillar and run scope
    cur.execute("""SELECT source_kind, scope_kind, scope_id FROM bundle_embeddings
                    WHERE run_id = %s ORDER BY source_kind, scope_kind, scope_id""",
                (res.run_id,))
    rows = {tuple(r) for r in cur.fetchall()}
    for kind in ("evidence", "score_rationale"):
        for scope in (("cell", "P1C1.1.1"), ("category", "P1C1"),
                      ("pillar", "P1"), ("run", None)):
            assert (kind,) + scope in rows
    # the deep-dive lands at its pillar; the exec summary only at run scope
    assert ("report_section", "pillar", "P1") in rows
    assert not any(k == "report_section" and s == "cell" for k, s, _ in rows)

    # centroids: correct thresholds, run scope keyed by '', unit length
    cur.execute("""SELECT scope_kind, scope_id, member_n, threshold,
                          abs(1 - vector_norm(centroid)) < 1e-6
                     FROM bundle_centroids WHERE run_id = %s""", (res.run_id,))
    cents = {r[0] + ":" + r[1]: r[2:] for r in cur.fetchall()}
    assert cents["cell:P1C1.1.1"][1] == pytest.approx(THRESHOLDS["cell"])
    assert cents["run:"][1] == pytest.approx(THRESHOLDS["run"])
    assert all(unit for _, _, unit in cents.values())
    # member_n is written even below five — the submit check abstains, we don't
    assert cents["cell:P1C1.1.1"][0] >= 2   # evidence + rationale

    # embedding_model is pinned on every row
    cur.execute("""SELECT DISTINCT embedding_model FROM bundle_embeddings
                    WHERE run_id = %s""", (res.run_id,))
    assert [r[0] for r in cur.fetchall()] == ["stub-encoder-384"]

    # re-embedding replaces wholesale, never accumulates
    stats2 = embed_run(worker, res.run_id, StubEncoder(), rationales)
    cur.execute("SELECT count(*) FROM bundle_embeddings WHERE run_id = %s", (res.run_id,))
    assert cur.fetchone()[0] == stats["embeddings"] == stats2["embeddings"]
