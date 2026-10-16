"""The DB's generated band and the ONE frontend resolver agree on every score
(invariant 6: "DB generated column ≡ frontend resolver; fixture test asserts
agreement for every score").

The resolver is `apps/web/lib/bands.js`'s `bandFor`, executed by node — not a
Python transcription of it, which would agree with the DB by construction and
prove nothing about the file the browser loads. The DB side is the generated
`band` on `heatmap_workbook_scores` and `overview_scores`, written the way the
promote writer writes them since 0064: the payload value into the 2dp display
column and, unscaled, into the raw column the band is generated from.

The fixture is every score from 1.000 to 5.000 in steps of 0.001 plus the
raw windows just below each boundary (x.995 .. x.9999) — the values the golden
run cannot exercise because no workbook happens to state them, and exactly
the ones a band generated from the 2dp copy gets wrong. A guard asserts the
2dp copy WOULD disagree on those windows, so the test cannot pass by banding
both sides from the same rounded number.

Backfilled rows (`*_raw_backfilled`) are excluded by construction: their raw
is a 2dp copy, so agreement on them proves nothing about raw banding.
"""
import json
import os
import shutil
import subprocess
import uuid
from decimal import Decimal as D
from pathlib import Path

import pytest

pg8000 = pytest.importorskip("pg8000.dbapi")

ROOT = Path(__file__).resolve().parents[2]
BANDS_JS = ROOT / "apps" / "web" / "lib" / "bands.js"
DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql+pg8000://postgres:local@localhost:5432/dma_insights")


def _connect():
    rest = DSN.split("@", 1)[1]
    hostport, _, database = rest.partition("/")
    host, _, port = hostport.partition(":")
    creds = DSN.split("://", 1)[1].split("@", 1)[0]
    user, _, password = creds.partition(":")
    return pg8000.connect(user=user, password=password, host=host,
                          port=int(port or 5432), database=database or "dma_insights")


@pytest.fixture(scope="module")
def db():
    try:
        conn = _connect()
    except Exception as e:                                     # noqa: BLE001
        pytest.skip(f"no migrated local database: {e}")
    yield conn
    conn.rollback()
    conn.close()


def q(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall() if cur.description else None


def _windows() -> set:
    """Just below each boundary, where a 2dp copy rounds UP into the next
    band, plus the boundaries themselves and SWBC's 2.0073."""
    below = {f"{b}.{tail}" for b in (1, 2, 3) for tail in
             ("995", "996", "999", "9949", "9951", "9999", "99999")}
    return below | {"1", "2", "3", "4", "5", "2.0", "4.00", "2.0073"}


def _scores() -> list[str]:
    # The text is what PostgreSQL hands back for the same NUMERIC (input
    # scale is kept), so it keys the resolver's answers directly.
    grid = {str(D(i) / D(1000)) for i in range(1000, 5001)}
    return sorted(grid | _windows(), key=D)


def _resolver(values: list[str]) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed; the resolver is a JS module")
    script = (
        f"import {{ bandFor }} from {json.dumps(BANDS_JS.as_uri())};\n"
        "let raw = '';\n"
        "process.stdin.on('data', c => raw += c);\n"
        "process.stdin.on('end', () => {\n"
        "  const vals = JSON.parse(raw);\n"
        "  const out = {};\n"
        "  for (const v of vals) out[v] = bandFor(v === null ? null : Number(v));\n"
        "  out['__null__'] = bandFor(null);\n"
        "  process.stdout.write(JSON.stringify(out));\n"
        "});\n")
    res = subprocess.run([node, "--input-type=module", "-e", script],
                         input=json.dumps(values), capture_output=True,
                         text=True, timeout=60, check=True)
    return json.loads(res.stdout)


def test_the_grid_band_equals_the_resolver_for_every_score(db):
    values = _scores()
    js = _resolver(values)
    assert js["__null__"] is None, "null -> no score, no band"
    db.rollback()
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
    rid = q(db, """INSERT INTO runs (entity_id, run_seq, status)
                   SELECT id, 1, 'PROMOTED' FROM entities WHERE display_id=%s
                   RETURNING id""", (eid,))[0][0]
    # the promote writer's shape: one payload value into both columns
    q(db, """INSERT INTO heatmap_workbook_scores
               (run_id, subcap_id, score, score_raw, promoted_at, producer_version)
             SELECT %s, 'S' || ord, v::numeric, v::numeric, now(), 'qa'
               FROM unnest(%s::text[]) WITH ORDINALITY AS t(v, ord)""",
      (rid, values))
    q(db, """INSERT INTO heatmap_workbook_scores
               (run_id, subcap_id, score, score_raw, promoted_at, producer_version)
             VALUES (%s, 'S-null', NULL, NULL, now(), 'qa')""", (rid,))
    rows = q(db, """SELECT score_raw::text, enum_label(band), score
                      FROM heatmap_workbook_scores
                     WHERE run_id = %s AND NOT score_raw_backfilled""", (rid,))
    assert len(rows) == len(values) + 1
    disagree, would_have = [], 0
    for raw, band, display in rows:
        if raw is None:
            assert band is None
            continue
        want = js[raw]
        if band != want:
            disagree.append((raw, band, want))
        if _resolver_py(display) != want:
            would_have += 1
    assert not disagree, f"DB band != bands.js bandFor on {disagree[:10]}"
    # Sensitivity guard: the 2dp copy bands differently on the windows, so a
    # pass here is a pass on the RAW value.
    assert would_have >= 6, would_have
    db.rollback()


def _resolver_py(v):
    """Only for the sensitivity guard above — never the comparison itself."""
    if v is None:
        return None
    s = float(v)
    return ("Activating" if s < 2 else "Building" if s < 3
            else "Competing" if s < 4 else "Differentiating")


def test_the_hero_band_equals_the_resolver_at_every_boundary_window(db):
    stride = {str(D(i) / D(1000)) for i in range(1000, 5001, 37)}
    values = sorted(_windows() | stride, key=D)
    js = _resolver(values)
    db.rollback()
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
    q(db, """INSERT INTO runs (entity_id, run_seq, status)
             SELECT e.id, ord, 'SUPERSEDED'
               FROM entities e, generate_series(1, %s) AS ord
              WHERE e.display_id = %s""", (len(values), eid))
    q(db, """INSERT INTO overview_scores
               (run_id, composite, composite_raw, promoted_at, producer_version)
             SELECT r.id, t.v::numeric, t.v::numeric, now(), 'qa'
               FROM unnest(%s::text[]) WITH ORDINALITY AS t(v, ord)
               JOIN runs r ON r.run_seq = t.ord
               JOIN entities e ON e.id = r.entity_id AND e.display_id = %s""",
      (values, eid))
    rows = q(db, """SELECT os.composite_raw::text, enum_label(os.band)
                      FROM overview_scores os
                      JOIN runs r ON r.id = os.run_id
                      JOIN entities e ON e.id = r.entity_id
                     WHERE e.display_id = %s AND NOT os.composite_raw_backfilled""",
             (eid,))
    assert len(rows) == len(values)
    bad = [(raw, band, js[raw]) for raw, band in rows if band != js[raw]]
    assert not bad, f"hero band != bands.js bandFor on {bad[:10]}"
    db.rollback()
