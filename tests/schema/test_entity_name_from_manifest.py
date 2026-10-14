"""0067 names a nameless entity from its own manifest, verbatim, and only
where no name exists (owner, 2026-10-05: names are hyphenated only if they
are originally so — a slug is never a name)."""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "migrations" / "versions" / "0067_entity_name_from_manifest.py"


def _load():
    prior = sys.modules.get("alembic")
    sys.modules["alembic"] = types.SimpleNamespace(op=None)
    try:
        spec = importlib.util.spec_from_file_location("_m0067", MIG)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if prior is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = prior
    return mod


def test_the_revision_follows_0066():
    m = _load()
    assert m.revision == "0067" and m.down_revision == "0066"


def test_only_a_wholly_nameless_entity_is_touched():
    q = _load()._CANDIDATES
    assert "e.legal_name IS NULL" in q and "e.trading_name IS NULL" in q
    src = MIG.read_text()
    up = src.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
    assert "legal_name IS NULL AND trading_name IS NULL" in up
    assert "SET trading_name" in up and "SET legal_name" not in up


def test_the_name_is_read_verbatim_from_the_manifest_never_from_the_slug():
    q = _load()._CANDIDATES
    assert "{manifest,institution,name}" in q
    assert "lower(n.name) <> lower(e.display_id)" in q, \
        "a slug written back as a name is the defect, stored"
    assert "replace(" not in q.lower() and "initcap" not in q.lower(), \
        "no de-slugging: punctuation the slug dropped cannot be guessed"


def test_downgrade_clears_only_what_it_wrote_and_refreshes():
    src = MIG.read_text()
    down = src.split("def downgrade", 1)[1]
    assert "trading_name = :v" in down and "legal_name IS NULL" in down
    assert "refresh_serving_directory()" in src
