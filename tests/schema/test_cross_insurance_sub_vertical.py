"""0066 fills Cross Insurance Agency's sub_vertical, and only where empty."""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "migrations" / "versions" / "0066_cross_insurance_sub_vertical.py"


def _load():
    prior = sys.modules.get("alembic")
    sys.modules["alembic"] = types.SimpleNamespace(op=None)
    try:
        spec = importlib.util.spec_from_file_location("_m0066", MIG)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if prior is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = prior
    return mod


def test_the_revision_chain_and_the_owners_value():
    m = _load()
    assert m.revision == "0066" and m.down_revision == "0065"
    assert m.DISPLAY_ID == "cross-insurance-agency"
    assert {c: v for c, v, _ in m._FILL} == {"sub_vertical": "IB"}


def test_every_write_is_guarded_and_fill_only():
    src = MIG.read_text()
    up = src.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
    assert "IS NULL" in up and "display_id = :d" in up
    down = src.split("def downgrade", 1)[1]
    assert "= CAST(:v AS" in down and "display_id = :d" in down
    assert "refresh_serving_directory()" in src
    assert "legal_name" not in up      # G-006 open: no name is written
