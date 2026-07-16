"""Lean-worker import contract (2026-06-11 prod incident).

The drive-crawler workers image excludes fastapi (d29a8b2). A lazy
`import fastapi` anywhere in the per-folder ingest chain crashes every
folder at runtime ("ModuleNotFoundError: No module named 'fastapi'" —
Cloud Run execution tlzfr). Pin: the full ingest chain must import
with fastapi BLOCKED.
"""
from __future__ import annotations

import subprocess
import sys

INGEST_CHAIN = [
    "app.services.parsers.dma_package",
    "app.services.parsers.package_persist",
    "app.services.alerts_producer",
    "app.services.artifact_manifest",
    "app.services.post_commit_workers",
    "app.scripts.historical_backfill",
]

_BLOCKER = (
    "import sys\n"
    "class _B:\n"
    "    def find_module(self, name, path=None):\n"
    "        return self if name == 'fastapi' or name.startswith('fastapi.') else None\n"
    "    def load_module(self, name):\n"
    "        raise ModuleNotFoundError(\"No module named 'fastapi' (lean-worker pin)\")\n"
    "sys.meta_path.insert(0, _B())\n"
)


def test_ingest_chain_never_imports_fastapi() -> None:
    code = _BLOCKER + "".join(f"import {m}\n" for m in INGEST_CHAIN) + "print('LEAN-OK')"
    res = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
    )
    assert "LEAN-OK" in res.stdout, (
        f"ingest chain pulled fastapi into the lean worker:\n{res.stderr[-1500:]}"
    )
