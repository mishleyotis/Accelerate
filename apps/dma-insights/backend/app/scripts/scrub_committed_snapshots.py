"""D4 — one-time scrub of already-committed startup-data snapshots.

The committed per-client JSON snapshots predate the D1.4 parser-warning
sanitize, the D2.5 SCQA "0.00 overall" fix, and the D2.6 jargon scrub.
Until the 94 packages are re-ingested + re-exported (D3, ingest env),
this applies the SAME hygiene DIRECTLY to the committed JSON so users
aren't served pydantic docs-URLs, malformed source_urls, the all-zero
SCQA, or internal jargon (P#C# / E-IDs / M-bands / "subcap" / the
"Severity-to-Maturity Cap Matrix" label / the "*Derived from extracted
scores*" footer).

Four defect classes:
  1. parser_warnings  — truncate each warning to its first line (drops the
                        multi-line pydantic blob incl. errors.pydantic.dev),
                        capped at 200 chars.
  2. source_url       — an http(s) URL containing whitespace is malformed
                        ("https://x (… enrichment)"); keep the URL token only.
  3. narrative *_md   — every markdown body (incl. per_pillar_md /
                        per_subcap_md dict values) → `scrub_md`.
  4. all-zero SCQA    — a DERIVED scqa_md built from placeholder 0.0 scores
                        ("scores 0.00 overall … (0.0)") is wholly false →
                        drop it (matches the fixed build_derived_scqa's None),
                        letting the UI fall back to its honest empty state.

Idempotent — re-running once clean is a no-op. Run from backend/:

    python -m app.scripts.scrub_committed_snapshots          # rewrite in place
    python -m app.scripts.scrub_committed_snapshots --check   # exit 1 if dirty
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from app.services.text_hygiene import scrub_md

# backend/app/scripts/this.py → repo .../apps/dma-insights/startup-data/clients
_CLIENTS = (
    Path(__file__).resolve().parents[3] / "startup-data" / "clients"
)

# A derived SCQA whose overall AND every category reads 0.0 — the
# all-placeholder bug (real scores live elsewhere in the same snapshot).
_ALL_ZERO_SCQA = re.compile(r"scores 0\.0+ overall", re.I)


def _clean_warning(v: str) -> str:
    """First line only, capped — strips the multi-line pydantic blob
    (and its errors.pydantic.dev docs URL) from a committed warning."""
    return v.split("\n", 1)[0].strip()[:200]


def _clean_source_url(v: str) -> str:
    """A real URL has no spaces; 'https://x (… enrichment)' is malformed.
    Keep the leading URL token only."""
    if v.startswith(("http://", "https://")) and (" " in v.strip()):
        return v.strip().split()[0]
    return v


def _scrub_node(node: Any) -> tuple[Any, int]:
    """Recursively scrub a JSON node. Returns (new_node, n_changes)."""
    changed = 0
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k == "parser_warnings" and isinstance(v, dict):
                nv = {wk: _clean_warning(wv) if isinstance(wv, str) else wv
                      for wk, wv in v.items()}
                changed += sum(1 for wk in v
                               if isinstance(v[wk], str) and v[wk] != nv[wk])
                out[k] = nv
            elif k == "parser_warnings" and isinstance(v, list):
                nv = [_clean_warning(x) if isinstance(x, str) else x for x in v]
                changed += sum(1 for a, b in zip(v, nv, strict=False) if a != b)
                out[k] = nv
            elif k == "source_url" and isinstance(v, str):
                nv = _clean_source_url(v)
                changed += nv != v
                out[k] = nv
            elif k == "scqa_md" and isinstance(v, str) and _ALL_ZERO_SCQA.search(v):
                # Wholly-false all-zero derived SCQA → drop (None).
                changed += 1
                out[k] = None
            elif k.endswith("_md") and isinstance(v, str):
                nv = scrub_md(v)
                changed += (nv or "") != v
                out[k] = nv
            elif k.endswith("_md") and isinstance(v, dict):
                # per_pillar_md / per_subcap_md: scrub each string value.
                nv = {dk: (scrub_md(dv) if isinstance(dv, str) else dv)
                      for dk, dv in v.items()}
                changed += sum(
                    1 for dk in v
                    if isinstance(v[dk], str) and (nv[dk] or "") != v[dk]
                )
                out[k] = nv
            else:
                sub, c = _scrub_node(v)
                changed += c
                out[k] = sub
        return out, changed
    if isinstance(node, list):
        new_list = []
        for v in node:
            sub, c = _scrub_node(v)
            changed += c
            new_list.append(sub)
        return new_list, changed
    return node, 0


def main(argv: list[str] | None = None) -> int:
    check = "--check" in (argv or sys.argv[1:])
    if not _CLIENTS.is_dir():
        print(f"ERROR: clients dir not found: {_CLIENTS}", file=sys.stderr)
        return 2
    files = sorted(_CLIENTS.glob("**/*.json"))
    dirty_files = 0
    total_changes = 0
    for f in files:
        try:
            original = f.read_text(encoding="utf-8")
            data = json.loads(original)
        except (OSError, json.JSONDecodeError) as e:
            print(f"skip {f.name}: {e}", file=sys.stderr)
            continue
        scrubbed, changes = _scrub_node(data)
        if changes:
            dirty_files += 1
            total_changes += changes
            if not check:
                # Match the committed serialization EXACTLY (indent=2,
                # sort_keys, ensure_ascii, trailing newline) so the diff is
                # content-only — verified by round-trip against the export.
                f.write_text(
                    json.dumps(scrubbed, indent=2, sort_keys=True,
                               ensure_ascii=True) + "\n",
                    encoding="utf-8",
                )
    verb = "would change" if check else "changed"
    print(f"# scrub_committed_snapshots: {verb} {total_changes} field(s) "
          f"across {dirty_files}/{len(files)} file(s)")
    if check and dirty_files:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
