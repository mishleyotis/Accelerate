"""Shared helpers for the check_consistency.py suites: write a run directory
of page payloads, run the checker as a producer would, return its report."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "plugins" / "dma-insights" / "skills" / "dma-surface-production"
          / "scripts" / "check_consistency.py")


def rundir(tmp_path: Path, pages: dict, bundle: dict | None = None,
           name: str = "run", **extra) -> Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    for page, body in pages.items():
        (d / f"{page}.json").write_text(json.dumps(body), encoding="utf-8")
    if bundle is not None:
        (d / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    for fname, body in extra.items():
        (d / f"{fname}.json").write_text(json.dumps(body), encoding="utf-8")
    return d


def run(d: Path, *args) -> tuple[int, str]:
    out = subprocess.run([sys.executable, str(SCRIPT), str(d), *args],
                         capture_output=True, text=True, cwd=str(ROOT))
    return out.returncode, out.stdout + out.stderr


def blocks(text: str, label: str) -> list[str]:
    """The message lines of every BLOCK issue under `label`."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if line.strip().startswith("[BLOCK]") and line.strip()[len("[BLOCK]"):].strip() == label:
            out.append(lines[i + 1].strip() if i + 1 < len(lines) else "")
    return out
