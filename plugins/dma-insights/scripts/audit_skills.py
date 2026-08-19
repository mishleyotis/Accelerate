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


# Set from the parsed arguments in main(); the audit functions read these.
ROOT = DEFAULT_ROOT
PLUGIN_ROOT = _plugin_root(DEFAULT_ROOT)
SKILLS: list = []
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


def help_audit():
    rows = []
    for s in SKILLS:
        for p in scripts(s):
            try:
                r = subprocess.run([sys.executable, p, "--help"],
                                   capture_output=True, text=True, timeout=60,
                                   cwd=os.path.dirname(p))
                rc, err = r.returncode, (r.stderr or "").strip().splitlines()
            except Exception as exc:
                rc, err = 99, [repr(exc)]
            reason = ""
            if rc != 0:
                tail = [l for l in err if "Error" in l or "error" in l]
                reason = (tail[-1] if tail else (err[-1] if err else ""))[:160]
            rows.append({"skill": s, "path": os.path.relpath(p, ROOT),
                         "rc": rc, "reason": reason})
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
                    cands = [
                        os.path.join(os.path.dirname(fp), tok),
                        os.path.join(base, tok),
                        os.path.join(base, "scripts", tok),
                        os.path.join(ROOT, tok),
                    ]
                    if any(os.path.exists(os.path.normpath(c)) for c in cands):
                        continue
                    if tok.startswith(RUNTIME_PREFIX) or RUNTIME_RE.match(tok):
                        runtime.append(row)
                    else:
                        broken.append(row)
    return broken, runtime


def main(argv=None) -> None:
    global ROOT, PLUGIN_ROOT, SKILLS
    ap = argparse.ArgumentParser(
        prog="audit_skills", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", nargs="?", default=DEFAULT_ROOT,
                    help="skills directory to audit "
                         "(default: the plugin's own skills/)")
    args = ap.parse_args(argv)
    ROOT = args.root
    PLUGIN_ROOT = _plugin_root(ROOT)
    SKILLS = _discover_skills(ROOT)
    h = help_audit()
    broken, runtime = refs_audit()
    fails = [x for x in h if x["rc"] != 0]
    print(json.dumps({
        "scripts_total": len(h), "scripts_ok": len(h) - len(fails),
        "scripts_fail": len(fails), "fails": fails,
        "broken_refs_total": len(broken), "broken_refs": broken,
        "runtime_paths_total": len(runtime),
        "runtime_by_skill": {s: sum(1 for x in runtime if x["skill"] == s)
                             for s in SKILLS},
    }, indent=1))


if __name__ == "__main__":
    main()
