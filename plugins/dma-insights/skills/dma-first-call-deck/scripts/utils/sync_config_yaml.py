#!/usr/bin/env python3
"""
sync_config_yaml.py — Verify that color_level_system.yaml mirrors color_level_system.py.

Checks every value in the YAML against the authoritative Python module. Any drift
causes an exit-code-1 failure. The YAML is advisory/human-readable; the Python
module is the source of truth.

Usage:
    python3 scripts/utils/sync_config_yaml.py
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BRAND = _HERE.parent.parent / "references" / "01_brand"
sys.path.insert(0, str(_BRAND))

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml --break-system-packages", file=sys.stderr)
    sys.exit(1)

import color_level_system as cls  # noqa: E402


YAML_PATH = _BRAND / "color_level_system.yaml"


def load_yaml():
    with open(YAML_PATH) as f:
        return yaml.safe_load(f)


def compare_level_4tier(yml, py, issues):
    ym = yml.get("level_4tier", {})
    for level_name in py.keys():
        if level_name not in ym:
            issues.append(f"YAML missing level_4tier[{level_name!r}]")
            continue
        y = ym[level_name]
        p = py[level_name]
        for key in ("accent", "card_bg", "label_text"):
            if y.get(key) != p[key]:
                issues.append(f"level_4tier[{level_name}].{key}: YAML={y.get(key)!r}, PY={p[key]!r}")
        yrange = tuple(y.get("score_range", ()))
        if yrange != tuple(p["score_range"]):
            issues.append(f"level_4tier[{level_name}].score_range: YAML={yrange}, PY={p['score_range']}")


def compare_level_5tier(yml, py, issues):
    ym = yml.get("level_5tier", {})
    for level_num in py.keys():
        if level_num not in ym:
            issues.append(f"YAML missing level_5tier[{level_num}]")
            continue
        y = ym[level_num]
        p = py[level_num]
        for key in ("label", "bg_rect", "circle", "num_text", "label_text"):
            if y.get(key) != p[key]:
                issues.append(f"level_5tier[{level_num}].{key}: YAML={y.get(key)!r}, PY={p[key]!r}")
        yrange = tuple(y.get("score_range", ()))
        if yrange != tuple(p["score_range"]):
            issues.append(f"level_5tier[{level_num}].score_range: YAML={yrange}, PY={p['score_range']}")


def compare_static_colors(yml, py, issues):
    ym = yml.get("static_colors", {}) or {}
    yml_keys = set(ym.keys())
    py_keys = set(py.keys())
    for k in py_keys - yml_keys:
        issues.append(f"YAML missing static_colors[{k!r}]")
    for k in yml_keys - py_keys:
        issues.append(f"YAML has extra static_colors[{k!r}] not in PY")
    for k in yml_keys & py_keys:
        if ym[k] != py[k]:
            issues.append(f"static_colors[{k!r}]: YAML={ym[k]!r}, PY={py[k]!r}")


def compare_theme_refs(yml, py, issues):
    ym = yml.get("theme_refs", {}) or {}
    yml_keys = set(ym.keys())
    py_keys = set(py.keys())
    for k in py_keys - yml_keys:
        issues.append(f"YAML missing theme_refs[{k!r}]")
    for k in yml_keys - py_keys:
        issues.append(f"YAML has extra theme_refs[{k!r}] not in PY")
    for k in yml_keys & py_keys:
        if ym[k] != py[k]:
            issues.append(f"theme_refs[{k!r}]: YAML={ym[k]!r}, PY={py[k]!r}")


def compare_blocks_and_order(yml, issues):
    if tuple(yml.get("blocks_158", [])) != tuple(cls.BLOCKS_158):
        issues.append("blocks_158 mismatch between YAML and PY")
    if tuple(yml.get("capability_order", [])) != tuple(cls.CAPABILITY_ORDER):
        issues.append("capability_order mismatch between YAML and PY")


def main():
    issues = []
    yml = load_yaml()
    compare_level_4tier(yml, cls.LEVEL_4TIER, issues)
    compare_level_5tier(yml, cls.LEVEL_5TIER, issues)
    compare_static_colors(yml, cls.STATIC_COLORS, issues)
    compare_theme_refs(yml, cls.THEME_REFS, issues)
    compare_blocks_and_order(yml, issues)

    if issues:
        print(f"[FAIL] YAML mirror diverges from Python module ({len(issues)} issue(s)):\n")
        for i in issues:
            print(f"  {i}")
        sys.exit(1)
    else:
        print("[OK] color_level_system.yaml is in sync with color_level_system.py")
        sys.exit(0)


if __name__ == "__main__":
    main()
