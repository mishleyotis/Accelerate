#!/usr/bin/env python3
"""Replay the connector's PASS 2 locally, before a submission is spent.

    pass2_replay.py <run_id> <page> --sections DIR [--json]

`local_precheck` (ship_page.py) runs pass 1 — the gates that need nothing
but the payload. Pass 2 is the half that needs the run: does every cited id
resolve to THIS entity, is a rung undated while its evidence holds a date
(CG-10), does a cell id resolve to a cell the run serves (CG-14), does the
prose name another client (ET-09), does a named product appear in its cited
excerpt (CG-50), is a technographic scan cited (ET-12)…  First Tech's
heatmap (2026-10-06) passed pass 1 clean and was then refused by the server
on CG-14, CG-10, CG-48, ET-09, AG-01 and AG-03 — a submission spent to learn
what the run's own facts already said.

This runs the server's OWN `validate_pass2` — imported, never restated —
against a read-only snapshot of the run assembled from the connector's read
tools (get_report_bundle, get_evidence, get_platform_fit, get_staged_payload,
list_pending_runs). The database calls the gates make are answered from that
snapshot. A query the snapshot cannot answer is NOT guessed: it raises, the
gate that issued it is reported under `unverified`, and the caller decides.
SG gates (V4 grounding, S8) disclose and still promote, so they are not
replayed here.

Exit 0 = pass-2 clean, 1 = blocking reasons, 2 = could not run.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MCP_RAW = HERE.parents[2] / "scripts" / "mcp_raw.py"


class Unanswered(RuntimeError):
    """A query the snapshot does not hold. Never answered with a guess."""


def mcp(tool: str, args: dict, timeout: int = 600) -> dict:
    p = subprocess.run([sys.executable, str(MCP_RAW), "call", tool, "--args",
                        json.dumps(args)], capture_output=True, text=True,
                       timeout=timeout)
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise RuntimeError(f"{tool}: {(p.stdout or p.stderr)[:300]}")


def _date(v):
    if not v:
        return None
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _names(obj, out: set):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("entity_name", "legal_name", "trading_name") and isinstance(v, str):
                out.add(v)
            else:
                _names(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _names(v, out)


class Snapshot:
    """The run's facts, fetched once through read-only connector tools."""

    def __init__(self, run_id: str, sections_dir: Path | None, call=None):
        self.call = call or mcp
        self.run_id = run_id
        self.sections_dir = sections_dir
        self.bundle = self.call("get_report_bundle", {"run_id": run_id})
        if not self.bundle.get("entity_id"):
            raise RuntimeError(f"get_report_bundle: {json.dumps(self.bundle)[:300]}")
        self.entity_id = self.bundle["entity_id"]
        self.ev: dict[str, dict] = {}        # cited id -> found row
        self.missing: set[str] = set()
        self.foreign: dict[str, str] = {}
        self._others = None
        self.unanswered: list[str] = []

    # ── evidence ────────────────────────────────────────────────────────
    def fetch(self, ids):
        todo = [i for i in dict.fromkeys(str(x) for x in ids)
                if i not in self.ev and i not in self.missing and i not in self.foreign]
        for k in range(0, len(todo), 150):
            chunk = todo[k:k + 150]
            r = self.call("get_evidence", {"run_id": self.run_id, "e_ids": chunk})
            if "found" not in r:
                raise RuntimeError(f"get_evidence: {json.dumps(r)[:300]}")
            for row in r["found"]:
                self.ev[row["e_id"]] = row
            self.missing.update(r.get("not_found") or [])
            for f in r.get("foreign") or []:
                self.foreign[f["e_id"]] = f["belongs_to"]

    def split(self, ids) -> dict:
        ids = [str(i) for i in ids]
        self.fetch(ids)
        return {"found": [self.ev[i] for i in ids if i in self.ev],
                "not_found": [i for i in ids if i in self.missing],
                "foreign": [{"e_id": i, "belongs_to": self.foreign[i]}
                            for i in ids if i in self.foreign]}

    def row(self, cited: str):
        """The evidence_index tuple evidence_tools._resolve returns."""
        cited = str(cited)
        self.fetch([cited])
        if cited in self.foreign:
            return (cited, self.foreign[cited]) + (None,) * 14
        r = self.ev.get(cited)
        if r is None:
            return None
        c = r.get("connector") or {}
        return (r.get("stored_id") or cited, r.get("entity_id"), r.get("source_name"),
                r.get("source_url"), r.get("excerpt"), r.get("claim_type"),
                r.get("tier"), _date(r.get("published_date")), r.get("recency_band"),
                r.get("ers"), r.get("origin"), r.get("customer_attribution"),
                r.get("split_of"), c.get("tool"), c.get("query"), c.get("retrieved_at"))

    def by_stored(self, stored: str):
        for r in self.ev.values():
            if r.get("stored_id") == stored or r.get("e_id") == stored:
                return r
        return None

    def successor(self, stored: str) -> list:
        """resolve_evidence_id (migration 0046): one hop onto the newest
        member of the -R<n> family, and only when that member carries links.
        The family is probed through get_evidence, which resolves stored ids."""
        base = re.sub(r"-R[0-9]+$", "", stored)
        m = re.search(r"-R([0-9]+)$", stored)
        own = int(m.group(1)) if m else 0
        fam = [base] + [f"{base}-R{n}" for n in range(1, 9)]
        self.fetch(fam)
        live = [(int(re.search(r"-R([0-9]+)$", i).group(1)) if "-R" in i[len(base):] else 0, i)
                for i in fam if i in self.ev]
        if not live:
            return []
        rn, head = max(live)
        row = self.ev[head]
        if rn <= own or head == stored or not row.get("linked_subcap_ids"):
            return []
        return [(head, len(row["linked_subcap_ids"]))]

    # ── corpus ──────────────────────────────────────────────────────────
    def others(self):
        if self._others is None:
            names: set = set()
            _names(self.call("list_pending_runs", {}), names)
            _names(self.call("list_withdrawn_runs", {}), names)
            mine = {str(self.bundle.get("entity_name") or ""),
                    str(self.bundle.get("trading_name") or "")}
            self._others = sorted(n for n in names if n and n not in mine)
        return self._others

    def sibling(self, page: str):
        if self.sections_dir is not None:
            local = load_sections(self.sections_dir, page)
            if local:
                return local
        idx = self.call("get_staged_payload", {"run_id": self.run_id, "page": page})
        out = {}
        for s in idx.get("sections") or []:
            name = s.get("name") if isinstance(s, dict) else s
            if not name:
                continue
            body = self.call("get_staged_payload", {"run_id": self.run_id, "page": page,
                                              "section": name})
            if isinstance(body.get("body"), dict):
                out[name] = body["body"]
            elif isinstance(body.get("section"), dict):
                out[name] = body["section"]
            else:
                raise Unanswered(f"staged {page}.{name} is described, not returned")
        return out or None


class Cursor:
    def __init__(self, snap: Snapshot):
        self.s = snap
        self._rows: list = []

    def execute(self, sql, params=()):
        q = " ".join(str(sql).split())
        b, s = self.s.bundle, self.s
        p = list(params or ())
        rows: list
        if q.startswith("INSERT INTO gate_results"):
            rows = []
        elif "FROM runs r JOIN entities e" in q and "r.entity_id, r.request_id" in q:
            rows = [(b["entity_id"], b.get("request_id"), b.get("run_seq"), b.get("entity_name"))]
        elif "e.sub_vertical, e.supplementary_sub_verticals" in q:
            rows = [(b.get("sub_vertical"), b.get("supplementary_sub_verticals") or [])]
        elif q.startswith("SELECT e.legal_name, e.trading_name FROM entities e WHERE e.id <>"):
            rows = [(n, None) for n in s.others()]
        elif "DISTINCT peer_name FROM peer_scores" in q:
            rows = [(n,) for n in sorted({r.get("peer_name") for r in b.get("peer_table") or []
                                          if r.get("peer_name")})]
        elif q.startswith("SELECT subcap_id, score FROM subcap_scores"):
            rows = [(r["subcap_id"], r.get("score")) for r in b.get("scores") or []]
        elif q.startswith("SELECT subcap_id FROM subcap_scores"):
            rows = [(r["subcap_id"],) for r in b.get("scores") or []]
        elif q.startswith("SELECT payload FROM run_manifest"):
            ro = b.get("rollups") or {}
            grains = {}
            if ro.get("pillars_basis") not in (None, "computed") and not ro.get("pillars_computed"):
                grains["pillars"] = ro.get("pillars") or []
            if ro.get("categories_basis") not in (None, "computed") and not ro.get("categories_computed"):
                grains["categories"] = ro.get("categories") or []
            rows = [({"workbook_grains": grains},)]
        elif "locked_peer_set" in q:
            s.unanswered.append("run_manifest.locked_peer_set (peer set read from peer_scores)")
            raise Unanswered("run_manifest.locked_peer_set")
        elif q.startswith("SELECT count(*) FROM recommendations_raw"):
            rows = [(len(b.get("recommendations") or []),)]
        elif "FROM evidence_index WHERE e_id = ANY" in q and "origin::text = 'connector'" in q:
            ids = [str(x) for x in (p[0] or [])]
            s.fetch(ids)
            n = sum(1 for i in ids if (s.ev.get(i) or {}).get("origin") == "connector"
                    and re.search(r"clay|vibe|explorium",
                                  str(((s.ev.get(i) or {}).get("connector") or {}).get("tool") or ""), re.I))
            rows = [(n,)]
        elif q.startswith("SELECT gate_id FROM gate_registry"):
            from dma_mcp.gates import GATES
            rows = [(g,) for g in (p[0] or []) if g in GATES]
        elif q.startswith("SELECT payload FROM submissions"):
            sib = s.sibling(p[1])
            rows = [(sib,)] if sib else []
        elif q.startswith("SELECT id FROM runs WHERE id"):
            rows = [(s.run_id,)]
        elif "FROM bundle_centroids" in q:
            rows = []                                   # SG-V4 is not replayed
        elif "FROM resolve_evidence_id(" in q:
            rows = s.successor(str(p[0]))
        elif "FROM evidence_subcap_links WHERE e_id" in q:
            r = s.by_stored(str(p[0]))
            rows = [(r.get("linked_subcap_ids") or [], r.get("seen_in_runs") or [])] if r else [(None, None)]
        else:
            s.unanswered.append(q[:160])
            raise Unanswered(q[:160])
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class Conn:
    def __init__(self, snap):
        self.snap = snap

    def cursor(self):
        return Cursor(self.snap)

    def commit(self):
        pass

    def rollback(self):
        pass


def load_sections(d: Path, page: str) -> dict:
    out = {}
    for f in sorted(Path(d).glob(f"{page}.*.json")):
        out[f.name[len(page) + 1:-5]] = json.loads(f.read_text())
    return out


def _connector_modules(repo: str | None):
    import importlib.util
    spec = importlib.util.spec_from_file_location("precheck_gates", HERE / "precheck_gates.py")
    pg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pg)
    validation, validation2, _rs, where = pg._load_connector(repo)
    return validation2, where


def replay(run_id: str, page: str, payload: dict, *, sections_dir=None,
           repo: str | None = None, call=None) -> dict:
    """→ {status: pass|fail|not_run, reasons, by_gate, unverified, why}"""
    try:
        v2, where = _connector_modules(repo)
        from dma_mcp import evidence_tools as ev, fit as fit_mod
        snap = Snapshot(run_id, Path(sections_dir) if sections_dir else None, call=call)
    except SystemExit as exc:
        return {"status": "not_run", "why": str(exc)[:300], "reasons": []}
    except Exception as exc:                                    # noqa: BLE001
        return {"status": "not_run", "why": f"{type(exc).__name__}: {exc}"[:300], "reasons": []}

    saved = (v2.get_evidence, ev.get_evidence, ev._resolve, fit_mod.platform_fit,
             v2._run_s8, v2._run_v4)

    def _get_evidence(conn, rid, ids):
        return snap.split(ids)

    def _resolve(cur, cited, scope):
        return snap.row(cited), True

    def _fit(conn, rid, candidates):
        r = snap.call("get_platform_fit", {"run_id": rid, "candidates": candidates})
        if r.get("_error") or r.get("error"):
            raise Unanswered(f"get_platform_fit: {json.dumps(r)[:160]}")
        return r

    v2.get_evidence = ev.get_evidence = _get_evidence
    ev._resolve = _resolve
    fit_mod.platform_fit = _fit
    v2._run_s8 = lambda *a, **k: []
    v2._run_v4 = lambda *a, **k: []
    try:
        reasons, _sg = v2.validate_pass2(Conn(snap), run_id, page, payload, encoder=None)
    except Unanswered as exc:
        return {"status": "not_run", "why": f"snapshot cannot answer: {exc}",
                "reasons": [], "gates_from": where}
    except Exception as exc:                                    # noqa: BLE001
        return {"status": "not_run", "why": f"validate_pass2 raised {type(exc).__name__}: {exc}"[:300],
                "reasons": [], "gates_from": where}
    finally:
        (v2.get_evidence, ev.get_evidence, ev._resolve, fit_mod.platform_fit,
         v2._run_s8, v2._run_v4) = saved
    blocking = [r for r in reasons if str(r.get("severity", "block")) == "block"
                and not str(r.get("gate_id", "")).startswith("SG")]
    unverified = [r for r in blocking if "Unanswered" in str(r.get("message"))
                  or "snapshot" in str(r.get("message"))]
    blocking = [r for r in blocking if r not in unverified]
    by_gate: dict[str, int] = {}
    for r in blocking:
        g = str(r.get("gate_id") or "?")
        by_gate[g] = by_gate.get(g, 0) + 1
    return {"status": "fail" if blocking else "pass", "reasons": blocking,
            "by_gate": by_gate, "gates_from": where,
            "unverified": sorted(set(snap.unanswered))
                          + [str(r.get("gate_id")) for r in unverified],
            "corpus_names": len(snap._others or [])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_id")
    ap.add_argument("pages", nargs="+")
    ap.add_argument("--sections", required=True)
    ap.add_argument("--repo")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    worst = 0
    out = {}
    for page in a.pages:
        payload = load_sections(Path(a.sections), page)
        if not payload:
            print(f"{page}: no section files — skipped")
            continue
        r = replay(a.run_id, page, payload, sections_dir=a.sections, repo=a.repo)
        out[page] = r
        if a.json:
            continue
        if r["status"] == "not_run":
            print(f"{page}: PASS 2 NOT RUN — {r['why']}")
            worst = max(worst, 2)
        elif r["status"] == "fail":
            print(f"{page}: PASS 2 FAIL — {len(r['reasons'])} blocking: "
                  + ", ".join(f"{g} x{n}" for g, n in sorted(r["by_gate"].items())))
            for x in r["reasons"][:40]:
                print("   ", x.get("gate_id"), x.get("path"), "|", str(x.get("message"))[:200])
            worst = max(worst, 1)
        else:
            print(f"{page}: PASS 2 clean")
        if r.get("unverified"):
            print(f"   unverified locally: {r['unverified'][:8]}")
    if a.json:
        print(json.dumps(out, indent=1, default=str))
        worst = max([0] + [{"pass": 0, "fail": 1, "not_run": 2}[r["status"]] for r in out.values()])
    return worst


if __name__ == "__main__":
    sys.exit(main())
