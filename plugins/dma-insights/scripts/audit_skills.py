#!/usr/bin/env python3
"""Audit the DMA skills: script --help exit codes and unresolved path refs.

Two classes of path token appear in these skills and only one of them can be
"broken":

  * a reference into the skill tree itself  — a sibling reference doc, a
    bundled script, a template. If it does not resolve, the reader follows a
    dead link. That is a defect.
  * a path in the CLIENT PACKAGE or the run's working tree — DMA_ROOT/...,
    04_scoring/Workbook.xlsx, working/deck.pptx, templates/<sv>.pptx
    (downloaded at runtime). These are outputs and inputs, not references.
    They cannot resolve at rest and it means nothing that they do not.

The second class is reported separately so it stops being counted as breakage.
"""
import argparse
import json
import os
import re
import subprocess
import sys

DEFAULT_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")


def _plugin_root(root: str) -> str:
    return (os.path.dirname(root.rstrip("/"))
            if root.rstrip("/").endswith("skills") else root)


def _repo_root(plugin_root: str) -> str:
    """The repository containing the plugin, or the plugin root if the audit is
    pointed at a tree that is not inside one (an unpacked zip, a fixture)."""
    d = os.path.abspath(plugin_root)
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.isdir(os.path.join(d, ".git")):
            return d
    return plugin_root


# Where THIS script lives, independent of what it is pointed at.
SELF_PLUGIN_ROOT = _plugin_root(DEFAULT_ROOT)
SELF_REPO = _repo_root(SELF_PLUGIN_ROOT)

# Set from the parsed arguments in main(); the audit functions read these.
ROOT = DEFAULT_ROOT
PLUGIN_ROOT = _plugin_root(DEFAULT_ROOT)
REPO_ROOT = _repo_root(PLUGIN_ROOT)
SKILLS: list = []

# THE RATCHET, and the reason this script now has an exit code at all.
#
# It reported 21 broken references and exited 0 — for every run it had ever
# made. A report nothing reads is not an audit, and CI could not adopt it
# while 12 of those 21 were the script's own resolution blind spots.
#
# Twelve are fixed above. The eight below are real dead links in skill
# markdown, which only the rectifier may edit (the weekly cycle owns skills,
# agents and gates), so they are pinned here rather than absorbed:
#
#   1  03-pages/rulebooks/heatmap.md -> shared/enrichment_gaps.py
#      — no file of that name exists anywhere in the repository
#   2-8 05-lifecycle/{surface-map,client-memory}.md -> rulebooks/*.md
#      — the rulebooks live under 03-pages/; these seven need that segment
#
# Lower it when the rectifier closes one. Raising it needs a reason in the
# commit that raises it.
# 8 -> 0 on 2026-08-29. The ceiling was set to exactly the then-current defect
# count, so the check passed while 49 of surface-map.md's 53 data rows pointed
# at `rulebooks/<page>.md` relative to 05-lifecycle/, where no such directory
# has ever existed (AUD-0005). A ratchet pinned to today's breakage cannot
# report breakage; the anchors are fixed, so the ceiling is 0 and the next
# broken reference fails the build.
MAX_BROKEN = 0
def _discover_skills(root):
    """Every skill directory under `root` that carries a SKILL.md, sorted.

    This was a hardcoded list of five names. A sixth skill was added and the
    auditor went on reporting a clean sweep of the five it knew about — the
    new skill's scripts and internal references were never checked, and the
    audit's own PASS was the reason nobody looked. That is the defect class
    this product keeps producing: a reader that does not recognise its input
    carries on as though the input were not there. Discovery cannot go
    stale; a list can, and silently.
    """
    if not os.path.isdir(root):
        raise SystemExit(f"audit_skills: no skills directory at {root}")
    found = sorted(d for d in os.listdir(root)
                   if os.path.isfile(os.path.join(root, d, "SKILL.md")))
    if not found:
        raise SystemExit(f"audit_skills: no SKILL.md under {root} — refusing "
                         "to report a clean audit of nothing")
    return found


# Prefixes that name the client package / run working tree, not the skill tree.
RUNTIME_PREFIX = (
    "DMA_ROOT/", "/checkpoints/", "checkpoints/", "working/", "research_audit/",
    "templates/cib_banking", "templates/commercial_lending", "templates/credit_unions",
    "templates/farm_credit", "templates/insurance_brokerages", "templates/insurance_carriers",
    "templates/retail_banking", "templates/wealth_asset_management", "templates/wealth_rias",
    "/home/claude/", "peers/", "unpacked/", "$DMA_ROOT/", "{DMA_ROOT}/",
    "deprecated/",  # appears only inside the SKILL.md ASCII tree diagram
    # `DMA Insights/state.json` and its siblings — the client's Drive tree,
    # written by drive_fetch.py push-bundle. PATH_RE cannot include the space,
    # so the token arrives clipped to "Insights/..." and read as a skill-tree
    # reference. It is a runtime path like every other entry here.
    "Insights/",
)
RUNTIME_RE = re.compile(r"^(/?\d\d[_a-z]*|.*?/\d\d_[a-z_]+)/")


def scripts(skill):
    base = os.path.join(ROOT, skill)
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "deprecated")]
        for f in filenames:
            if f.endswith(".py") and not f.startswith("_"):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


_MISSING_MODULE = re.compile(r"ModuleNotFoundError: No module named '([\w.]+)'")
# A script that catches its own ImportError and prints a clean install hint —
# "ERROR: openpyxl not installed. Run: pip install openpyxl" — is doing the
# RIGHT thing, and a classifier that reads only tracebacks marks exactly those
# scripts as broken. Eight of them, all better-behaved than the eighteen that
# let the traceback through.
_PIP_HINT = re.compile(r"pip install\s+(?:-[\w-]+\s+)*([A-Za-z][\w.-]*)")


def _is_first_party(mod: str) -> bool:
    """Does this repository ship the missing module?

    The distinction decides whether a failing `--help` is a DEFECT or a bare
    machine. `import openpyxl` failing says the runner has no openpyxl;
    `import dma_worker` failing says the script's own imports are wrong, and
    that is true on every machine.
    """
    top = mod.split(".")[0]
    seen = set()
    # SELF_REPO, not only the audited tree. "What this repository ships" is a
    # property of the auditor's own repository and does not change with the
    # directory you point it at — pointed at a temporary tree, the derived
    # roots are that tree, and `import dma_mcp` failing would be excused as a
    # missing third-party package.
    for base in (PLUGIN_ROOT, REPO_ROOT, SELF_PLUGIN_ROOT, SELF_REPO):
        if not base or base in seen:
            continue
        seen.add(base)
        roots = [base]
        for parent in ("apps", "packages", "scripts", "plugins"):
            p = os.path.join(base, parent)
            if os.path.isdir(p):
                roots.append(p)
                roots.extend(os.path.join(p, d) for d in os.listdir(p)
                             if os.path.isdir(os.path.join(p, d)))
        for r in roots:
            if os.path.exists(os.path.join(r, top)) or \
                    os.path.exists(os.path.join(r, top + ".py")):
                return True
    return False


def help_audit():
    rows = []
    for s in SKILLS:
        for p in scripts(s):
            try:
                r = subprocess.run([sys.executable, p, "--help"],
                                   capture_output=True, text=True, timeout=60,
                                   cwd=os.path.dirname(p))
                rc = r.returncode
                err = (r.stderr or "").strip().splitlines()
                # BOTH STREAMS. Several of these scripts print their install
                # hint on stdout, so a stderr-only read saw an empty reason and
                # had nothing to classify.
                out = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
            except Exception as exc:
                rc, err, out = 99, [repr(exc)], repr(exc)
            reason, kind, missing = "", "ok", ""
            if rc != 0:
                tail = [l for l in (err or out.splitlines())
                        if "Error" in l or "error" in l or "ERROR" in l]
                reason = (tail[-1] if tail
                          else (err[-1] if err else out.splitlines()[-1]
                                if out else ""))[:160]
                # A THIRD-PARTY IMPORT THE RUNNER LACKS IS NOT BREAKAGE.
                # Measured 2026-08-20: this audit gained an exit code and CI
                # went red with "17 script(s) fail --help" — seventeen skill
                # scripts whose only sin was wanting openpyxl on a runner that
                # installs the services' requirements and not the plugin's.
                # Reported, counted, and not fatal; a first-party import that
                # fails still is, because that one fails everywhere.
                m = _MISSING_MODULE.search(out) or _PIP_HINT.search(out)
                if m and not _is_first_party(m.group(1)):
                    kind, missing = "env", m.group(1)
                else:
                    kind = "fail"
            rows.append({"skill": s, "path": os.path.relpath(p, ROOT),
                         "rc": rc, "reason": reason, "kind": kind,
                         "missing": missing})
    return rows


PATH_RE = re.compile(
    r'(?<![\w/.-])((?:\$\{CLAUDE_PLUGIN_ROOT\}/)?(?:\.{0,2}/)?'
    r'(?:[\w.${}-]+/)+[\w.-]+'
    r'\.(?:py|json|md|csv|yaml|yml|xlsx|docx|pptx|potx|txt|sh))')
SKIP_PREFIX = ("http", "gs://", "apps/", "docs/", "packages/", "infra/",
               "migrations/", "fixtures/", "prototype/", "ppt/", "/mnt/")


def refs_audit():
    broken, runtime = [], []
    for s in SKILLS:
        base = os.path.join(ROOT, s)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for f in filenames:
                if not f.endswith((".md", ".json")):
                    continue
                fp = os.path.join(dirpath, f)
                try:
                    text = open(fp, encoding="utf-8").read()
                except Exception:
                    continue
                for m in sorted(set(PATH_RE.findall(text))):
                    tok = m.strip()
                    if tok.startswith(SKIP_PREFIX) or "://" in tok:
                        continue
                    row = {"skill": s, "file": os.path.relpath(fp, ROOT), "ref": tok}
                    if tok.startswith("${CLAUDE_PLUGIN_ROOT}/"):
                        real = os.path.join(
                            PLUGIN_ROOT, tok[len("${CLAUDE_PLUGIN_ROOT}/"):])
                        (runtime if False else broken).append(row) if not os.path.exists(real) else None
                        continue
                    # EVERY BASE A READER WOULD ACTUALLY TRY. The first four
                    # were the skill's own tree, so twelve references that
                    # resolve perfectly well — `scripts/agent_run.py` at the
                    # plugin root, `scripts/tests/...` at the repo root,
                    # `rulebooks/heatmap.md` from a sibling inside 03-pages —
                    # were reported as breakage. An audit whose finding list
                    # is mostly false is an audit nobody reads, which is how
                    # the eight real dead links below sat in it unnoticed.
                    cands = [
                        os.path.join(os.path.dirname(fp), tok),
                        os.path.join(base, tok),
                        os.path.join(base, "scripts", tok),
                        os.path.join(ROOT, tok),
                        # the plugin's own scripts/ and skills/ — what a bare
                        # `scripts/x.py` in a skill doc means at runtime
                        os.path.join(PLUGIN_ROOT, tok),
                        # the repository, for a doc pointing a DEVELOPER at a
                        # test or a design note rather than the reader at a
                        # runtime file
                        os.path.join(REPO_ROOT, tok),
                        # the section directory: `rulebooks/heatmap.md` written
                        # from inside 03-pages/rulebooks/ means its sibling
                        os.path.join(os.path.dirname(os.path.dirname(fp)), tok),
                    ]
                    if any(os.path.exists(os.path.normpath(c)) for c in cands):
                        continue
                    if tok.startswith(RUNTIME_PREFIX) or RUNTIME_RE.match(tok):
                        runtime.append(row)
                    else:
                        broken.append(row)
    return broken, runtime


def main(argv=None) -> int:
    global ROOT, PLUGIN_ROOT, REPO_ROOT, SKILLS
    ap = argparse.ArgumentParser(
        prog="audit_skills", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=DEFAULT_ROOT,
                    help="skills directory to audit "
                         "(default: the plugin's own skills/)")
    ap.add_argument("--max-broken", type=int, default=MAX_BROKEN,
                    help=f"fail above this many broken references "
                         f"(default: {MAX_BROKEN}, the pinned backlog)")
    args = ap.parse_args(argv)
    ROOT = args.root
    PLUGIN_ROOT = _plugin_root(ROOT)
    REPO_ROOT = _repo_root(PLUGIN_ROOT)
    SKILLS = _discover_skills(ROOT)
    h = help_audit()
    broken, runtime = refs_audit()
    fails = [x for x in h if x["kind"] == "fail"]
    env = [x for x in h if x["kind"] == "env"]
    print(json.dumps({
        "scripts_total": len(h), "scripts_ok": len(h) - len(fails) - len(env),
        "scripts_fail": len(fails), "fails": fails,
        "scripts_env": len(env),
        "env_modules": sorted({x["missing"] for x in env}),
        "broken_refs_total": len(broken), "broken_refs": broken,
        "broken_refs_ceiling": args.max_broken,
        "runtime_paths_total": len(runtime),
        "runtime_by_skill": {s: sum(1 for x in runtime if x["skill"] == s)
                             for s in SKILLS},
    }, indent=1))

    # THE EXIT CODE. Without it this script printed a defect list forever and
    # every caller read success. A failing --help is breakage outright; a
    # broken reference is breakage above the pinned backlog.
    if env:
        print(f"audit_skills: {len(env)} script(s) could not run --help for "
              f"want of {', '.join(sorted({x['missing'] for x in env}))} — "
              f"reported, not counted as breakage", file=sys.stderr)
    if fails:
        print(f"audit_skills: {len(fails)} script(s) fail --help: "
              f"{', '.join(x['path'] for x in fails[:5])}", file=sys.stderr)
        return 1
    if len(broken) > args.max_broken:
        print(f"audit_skills: {len(broken)} broken references, ceiling "
              f"{args.max_broken}. Fix them, or raise MAX_BROKEN in this file "
              f"with a reason in the commit that raises it.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
