"""Prose a customer reads, rewritten out of our search log.

The engine projects research notes into client surfaces (the heatmap cell
drawer's absence syntheses, `surface_export.absence_rows`). Those notes name
the tools that ran the searches and the budget they had, which the serve layer
deletes for the customer audience and the connector's CG-52 refuses at
submit. `client_safe(text)` keeps what the search established and drops the
plumbing, using the ONE rule both of those read:
packages/shared/internal_ids.py.

A repo checkout wins over the packaged copy (`data/internal_ids.py`), so a rule
change lands without a plugin release; the packaged copy exists so a
trigger-fired Cowork container with no checkout still writes client-safe
prose. tests/skills/research_engine/test_client_prose.py pins the packaged copy
byte-identical to the shared one.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_HERE = Path(__file__).resolve()


def _candidates() -> list[Path]:
    out = [anc / "packages" / "shared" / "internal_ids.py" for anc in _HERE.parents]
    out.append(_HERE.parent / "data" / "internal_ids.py")
    return out


def _load():
    for path in _candidates():
        if path.is_file():
            spec = importlib.util.spec_from_file_location("_dma_internal_ids", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise RuntimeError("internal_ids.py not found in a checkout or the packaged data/ "
                       "copy — the plugin is incomplete; reinstall it")


_IDS = _load()


def client_safe(text):
    """`text` with every pipeline term rewritten; guaranteed not to name one."""
    out = _IDS.neutralise_pipeline_terms(text)
    if isinstance(out, str) and _IDS.names_pipeline_term(out):
        raise ValueError(f"client_safe left a pipeline term in: {out[:160]!r}")
    return out


def names_pipeline_term(text):
    return _IDS.names_pipeline_term(text)
