"""The drawer's ETag has to change when the drawer's contents change.

`/v1/entities/{id}/evidence` is a LIVE read of `evidence_index` — not a
promoted page. Its tag was `run_id.promoted_epoch.audience`, which is right
for a page frozen at promotion and wrong for a table that changes without
one.

MEASURED 2026-09-04. Golden 1 Credit Union served 728 citations with 193
URLs. The worker's repair pass fills a null `source_url` from the package's
own workbook — no promotion, no `promoted_at` change — so every one of those
497 drawers gained a link while the tag stayed byte-identical. A browser
holding the old copy sends `If-None-Match`, the server answers 304, and the
client goes on rendering the blank drawer the fix was for. The repair would
have worked and nobody would have seen it.

So the tag carries a digest of the rows actually served, as a fourth
component beside `SERVE_RULES` — which is in the tag for exactly the same
reason one layer up: the same run serves different documents before and
after something outside the promotion changes.

Run with
`pytest apps/api/tests/test_the_evidence_tag_tracks_the_rows_it_serves.py`.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

pytest.importorskip("httpx", reason="fastapi.testclient needs httpx")
from fastapi.testclient import TestClient                      # noqa: E402

from dma_api import main                                       # noqa: E402

RUN = {"run_id": "11111111-2222-3333-4444-555555555555",
       "promoted_at": "2026-08-30T10:00:00+00:00"}
ENTITY = {"display_id": "golden-1-credit-union", "legal_name": "Golden 1"}


def _row(url):
    return {"e_id": "E-CC-569", "source_name": "DFPI record",
            "source_url": url, "excerpt": "x" * 60, "tier": "T1",
            "origin": "package"}


class _Conn:
    def cursor(self):
        return self

    def close(self):
        pass


@pytest.fixture()
def drawer(monkeypatch):
    """A drawer whose one row's URL the test can change under it, exactly as
    the worker's repair pass changes it in production."""
    state = {"url": None}

    def _fetch(cur, entity_id, wanted, run_id=None):
        return {"items": [_row(state["url"])], "found": [], "not_found": [],
                "foreign": [], "distribution": {}}

    monkeypatch.setattr(main, "_connect", lambda: _Conn())
    monkeypatch.setattr(main, "resolve_run",
                        lambda cur, display_id, run, history:
                        ("ent-1", ENTITY, dict(RUN), None))
    monkeypatch.setattr(main, "ev_fetch", _fetch)
    client = TestClient(main.app)

    def tag(url, headers=None):
        state["url"] = url
        return client.get("/v1/entities/golden-1-credit-union/evidence"
                          "?audience=internal", headers=headers or {})

    return tag


def _tag(drawer, url):
    r = drawer(url)
    assert r.status_code == 200
    return r.headers["etag"]


def test_filling_a_blank_url_changes_the_tag(drawer):
    """The whole point. Same run, same promotion, one drawer that gained a
    link — a client holding the old tag must be told to re-fetch."""
    blank = _tag(drawer, None)
    filled = _tag(drawer, "https://dfpi.ca.gov/golden-1")
    assert blank != filled, \
        "the tag ignored the URL the repair filled in, so every cached " \
        "client keeps being served the blank drawer"


def test_an_unchanged_drawer_still_answers_304(drawer):
    """The tag must not become a cache-buster: identical rows, identical tag,
    and `If-None-Match` still saves the body."""
    tag = _tag(drawer, "https://dfpi.ca.gov/golden-1")
    assert _tag(drawer, "https://dfpi.ca.gov/golden-1") == tag, \
        "identical content produced a different tag; nothing would ever cache"
    r = drawer("https://dfpi.ca.gov/golden-1",
               headers={"If-None-Match": tag})
    assert r.status_code == 304 and not r.content


def test_the_run_and_the_audience_are_still_in_the_tag(drawer):
    """The digest is an ADDITION to the documented triple, not a replacement:
    one run still serves two different documents, and they must not collide."""
    tag = _tag(drawer, "https://dfpi.ca.gov/golden-1")
    assert RUN["run_id"] in tag and "internal" in tag
