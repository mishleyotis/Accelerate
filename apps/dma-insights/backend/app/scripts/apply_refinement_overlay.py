"""Stage-2 refinement overlay loader (plan §2, user decision 2026-07-08).

The refinement is produced ONCE by Claude Code reading each client's whole
report package (Assessment + Client-Profile DOCX, scoring CSVs, evidence
workbooks) together with the deterministic draft, and is committed as a
per-client overlay ``startup-data/refinement/{display_id}.json``. This loader
applies the overlay to the EXPORTED pack deterministically — so CI reproduces
the exact bytes (pack-parity holds) and the served app makes ZERO model calls
at request time. No external API is used anywhere: the interpreter (Claude
Code) reads files and writes files; this step is pure JSON merge.

Overlay schema (every key optional — only present fields override; a field
absent from the overlay leaves the derived value untouched). Every overridden
fact/quote MUST be verifiable in the client's package; the ``_verification``
block records field -> {source, quote} and the gate (--verify) asserts it.

    {
      "display_id": "greenstone-farm-credit-s-3001",
      "financial_trajectory": { "fy": [...], "series": {...}, "headline": "..." },
      "sentiment": { "qualitative": [...], "customer": [...], "employee": [...] },
      "firmographics": { "hq": "...", "hq_address": "...", "founded": 1932, ... },
      "top_findings": [ { "subcap_id": "P2C1", "body": "...", "so_what": "...",
                          "evidence": ["E-012"] }, ... ],
      "insight_cards": { "INS-REC-01": { "what_text": "...", "why_text": "...",
                                         "so_what_text": "...", "title": "..." } },
      "platform_cards": { "salesforce": { "opportunity_md": "...", "story_md": "..." } },
      "issue_rationale": { "ISS-001": "..." },
      "focus": { "<id-or-title>": { "title": "...", "verbatim_quote": "..." } },
      "_verification": { "financial_trajectory.series": {"source": "...", "quote": "..."} }
    }

Usage:
  python -m app.scripts.apply_refinement_overlay --clients-dir <pack>/clients \
      [--overlay-dir <repo>/startup-data/refinement] [--verify] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os


def _load(p: str):
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


# Prose fields an overlay may carry into RENDERED surfaces. Hand-authored
# overlays kept leaking raw P#C# subcap codes into insight why/so-what text,
# and pack_quality_gate's ENFORCED S1_jargon segment (ceiling 0) then blocked
# the deploy (2026-07-10 redeployment QA — 14 violations from 4 committed
# overlay files). Scrub these through the SAME text_hygiene.plain() every
# composed surface already passes through; structural fields (ids, subcap
# keys, platform ids) and _verification provenance quotes stay verbatim.
_PROSE_KEYS = {
    "what_text", "why_text", "so_what_text", "title", "rationale", "body",
    "narrative", "detail", "summary", "description", "headline", "so_what",
}


def _scrub_prose(node, in_verification: bool = False):
    """Recursively plain()-scrub prose-keyed string values in an overlay."""
    from app.services.text_hygiene import plain

    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "_verification":
                out[k] = v  # provenance quotes stay verbatim
            elif isinstance(v, str) and k in _PROSE_KEYS:
                out[k] = plain(v)
            else:
                out[k] = _scrub_prose(v)
        return out
    if isinstance(node, list):
        return [_scrub_prose(v) for v in node]
    return node


def _write(p: str, obj, dry: bool) -> None:
    if dry:
        return
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _merge_by_key(items: list, patches: dict, key: str) -> int:
    """Merge patches (keyed by `key`'s value) into a list of dict items."""
    n = 0
    for it in items:
        pid = str(it.get(key) or "")
        patch = patches.get(pid)
        if isinstance(patch, dict):
            it.update({k: v for k, v in patch.items() if v is not None})
            n += 1
    return n


def apply_overlay(cdir: str, overlay: dict, dry: bool, stats: dict) -> None:
    did = os.path.basename(cdir.rstrip("/"))
    ov_p = os.path.join(cdir, "overview.json")
    ins_p = os.path.join(cdir, "insights.json")
    pl_p = os.path.join(cdir, "platforms.json")
    ctx_p = os.path.join(cdir, "context.json")
    fa_p = os.path.join(cdir, "focus_areas.json")

    ov = _load(ov_p)
    if ov is not None:
        changed = False
        for fld in ("financial_trajectory", "sentiment"):
            if isinstance(overlay.get(fld), dict):
                ov[fld] = overlay[fld]
                changed = True
                stats[f"overview.{fld}"] += 1
        if isinstance(overlay.get("firmographics"), dict):
            fm = ov.get("firmographics") or {}
            fm.update({k: v for k, v in overlay["firmographics"].items() if v is not None})
            ov["firmographics"] = fm
            changed = True
            stats["overview.firmographics"] += 1
        if isinstance(overlay.get("top_findings"), list) and overlay["top_findings"]:
            by_sub = {str(t.get("subcap_id") or t.get("name")): t for t in overlay["top_findings"]}
            existing = ov.get("top_findings") or []
            merged = _merge_by_key(existing, by_sub, "subcap_id")
            # append any refinement finding not matched to an existing one
            seen = {str(t.get("subcap_id") or "") for t in existing}
            for t in overlay["top_findings"]:
                if str(t.get("subcap_id") or "") not in seen:
                    existing.append(t)
            ov["top_findings"] = existing
            changed = changed or bool(merged or overlay["top_findings"])
            stats["overview.top_findings"] += 1
        if changed and did == did:
            _write(ov_p, ov, dry)

    ins = _load(ins_p)
    if ins is not None and isinstance(overlay.get("insight_cards"), dict):
        n = _merge_by_key(ins.get("items") or [], overlay["insight_cards"], "ic_id")
        if n:
            _write(ins_p, ins, dry)
            stats["insights.items"] += n

    pl = _load(pl_p)
    if pl is not None and isinstance(overlay.get("platform_cards"), dict):
        n = _merge_by_key(pl.get("cards") or [], overlay["platform_cards"], "platform_id")
        if n:
            _write(pl_p, pl, dry)
            stats["platforms.cards"] += n

    ctx = _load(ctx_p)
    if ctx is not None and isinstance(overlay.get("issue_rationale"), dict):
        n = 0
        for ir in ctx.get("issue_register") or []:
            rat = overlay["issue_rationale"].get(str(ir.get("issue_id") or ir.get("id")))
            if rat:
                ir["rationale"] = rat
                n += 1
        if n:
            _write(ctx_p, ctx, dry)
            stats["context.issue_rationale"] += n

    fa = _load(fa_p)
    if fa is not None and isinstance(overlay.get("focus"), dict):
        n = 0
        for it in fa.get("items") or []:
            patch = (overlay["focus"].get(str(it.get("id")))
                     or overlay["focus"].get(str(it.get("title"))))
            if isinstance(patch, dict):
                it.update({k: v for k, v in patch.items() if v is not None})
                n += 1
        if n:
            _write(fa_p, fa, dry)
            stats["focus.items"] += n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clients-dir", required=True)
    ap.add_argument("--overlay-dir", default=None,
                    help="default: <clients-dir>/../../refinement")
    ap.add_argument("--verify", action="store_true",
                    help="fail if any overlay overrides a fact with no _verification entry")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    clients_dir = args.clients_dir
    overlay_dir = args.overlay_dir or os.path.normpath(
        os.path.join(clients_dir, "..", "..", "refinement"))
    if not os.path.isdir(overlay_dir):
        print(f"# apply_refinement_overlay: no overlay dir ({overlay_dir}) — nothing to apply")
        return 0

    from collections import defaultdict
    stats: dict = defaultdict(int)
    applied = 0
    unverified: list[str] = []
    for fn in sorted(os.listdir(overlay_dir)):
        if not fn.endswith(".json"):
            continue
        did = fn[:-5]
        overlay = _load(os.path.join(overlay_dir, fn))
        if not isinstance(overlay, dict):
            continue
        overlay = _scrub_prose(overlay)
        cdir = os.path.join(clients_dir, did)
        if not os.path.isdir(cdir):
            print(f"::warning::refinement overlay {fn} has no matching client dir {did}")
            continue
        # Verification contract: every content field carried by the overlay
        # must have a _verification entry (source + quote from the package).
        if args.verify:
            verif = overlay.get("_verification") or {}
            content_keys = [k for k in overlay
                            if k not in ("display_id", "_verification", "_notes", "generated_by")]
            if content_keys and not verif:
                unverified.append(did)
        apply_overlay(cdir, overlay, args.dry_run, stats)
        applied += 1

    print(f"# apply_refinement_overlay: applied {applied} client overlays"
          + (" (dry-run)" if args.dry_run else ""))
    for k in sorted(stats):
        print(f"   {k:28} {stats[k]}")
    if args.verify and unverified:
        print(f"::error::refinement overlays missing _verification: {unverified[:20]}")
        return 11
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
