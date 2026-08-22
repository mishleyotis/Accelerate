#!/usr/bin/env python3
"""Build the claude.ai-uploadable zip of the dma-insights plugin.

The upload validator's rules arrive one failed upload at a time (a top-level
bin/ on 2026-08-20, then a 500-character description cap the same night), so
packaging is a script with a test rather than an ad-hoc zip command: every
rule the validator has ever named is asserted HERE, before a person burns an
upload attempt on it. `claude plugin validate` passes manifests the uploader
refuses — measured: it accepted a 734-character description — so the CLI
validator is necessary but nowhere near sufficient.

    python3 scripts/package_plugin.py [--out DIR]

Writes dma-insights-<version>.zip and prints one line per check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".DS_Store"}
EXCLUDE_SUFFIX = {".pyc"}

# Every rule the claude.ai upload validator has enforced against this plugin,
# with the date it was learned, plus documented rules worth failing early on.
# Add to this list; never remove.
DESCRIPTION_MAX = 500          # "at most 500 characters" (2026-08-20)
FORBIDDEN_TOP_LEVEL = {"bin"}  # "may not ship bin/ executables" (2026-08-20)
MAX_ZIP_BYTES = 50 * 1024 * 1024  # documented org-plugin cap
NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")  # kebab-case, documented
# Plugin-provided agents may not carry these front-matter fields (documented
# restriction; all sixteen agents carried mcpServers until 2026-08-20 —
# disallowedTools stays the actual guard, per-agent MCP scoping was
# defense-in-depth the hosted schema refuses).
FORBIDDEN_AGENT_KEYS = {"mcpServers", "hooks", "permissionMode"}


def iter_files():
    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(PLUGIN)
        if EXCLUDE_PARTS & set(rel.parts) or rel.suffix in EXCLUDE_SUFFIX:
            continue
        yield rel


def check(manifest: dict, entries: list) -> list:
    """Return failure strings; empty means uploadable as far as we know."""
    fails = []
    desc = manifest.get("description") or ""
    if len(desc) > DESCRIPTION_MAX:
        fails.append(f"description is {len(desc)} chars (max {DESCRIPTION_MAX})")
    if not re.search(r"\(\d+ tools\)", desc):
        fails.append("description lost its '(N tools)' count — doctor.py's "
                     "roster reconciliation parses it")
    tops = {str(e).split("/", 1)[0] for e in entries}
    for bad in FORBIDDEN_TOP_LEVEL & tops:
        fails.append(f"top-level {bad}/ present — claude.ai refuses PATH-added "
                     "executables")
    # The agents live in taxonomy folders (owner, 2026-08-20: "organized well
    # into folders and subfolders"). The manifest schema accepts individual
    # FILE paths only (directory entries fail validate), so plugin.json must
    # declare every agent file explicitly — the belt for any loader that does
    # not recurse into agents/ by default. Manifest and disk must be the same
    # set, or an agent exists that some loader will never see.
    declared = {a.lstrip("./") for a in manifest.get("agents", [])}
    on_disk = {e for e in (str(x) for x in entries)
               if e.startswith("agents/") and e.endswith(".md")
               and not e.endswith("README.md")}
    for missing in sorted(on_disk - declared):
        fails.append(f"agent file {missing} not declared in plugin.json "
                     f"agents[] — a non-recursive loader never sees it")
    for ghost in sorted(declared - on_disk):
        fails.append(f"plugin.json declares {ghost} but no such file ships")
    if ".claude-plugin/plugin.json" not in {str(e) for e in entries}:
        fails.append("manifest missing from archive root")
    if not re.fullmatch(r"\d+\.\d+\.\d+", manifest.get("version") or ""):
        fails.append(f"version {manifest.get('version')!r} is not semver")
    for e in entries:
        if "__pycache__" in str(e) or str(e).endswith(".pyc"):
            fails.append(f"bytecode shipped: {e}")
    if not NAME_RE.fullmatch(manifest.get("name") or ""):
        fails.append(f"name {manifest.get('name')!r} is not kebab-case")
    if re.search(r"https?://", desc):
        fails.append("description contains a URL — the uploader rejects them; "
                     "use homepage/repository fields")
    for agent in sorted(p for p in (PLUGIN / "agents").rglob("*.md")
                        if p.name != "README.md"):
        head = agent.read_text().split("---")[1]
        keys = {line.split(":")[0].strip() for line in head.splitlines()
                if ":" in line and not line.startswith((" ", "\t", "-", "#"))}
        for bad in sorted(FORBIDDEN_AGENT_KEYS & keys):
            fails.append(f"agents/{agent.name} front matter carries {bad} — "
                         "forbidden for plugin-provided agents")
    return fails


def flatten_agents(entries) -> dict:
    """Zip arcname per repo path: agents flatten to agents/<name>.md.

    Measured 2026-08-20, both directions, both by rejection: the claude.ai
    upload validator does NOT recurse into agents/ subdirectories and treats
    manifest `agents` entries as DIRECTORIES to scan ("No agent files found
    in specified directories"), while the CLI refuses to INSTALL a manifest
    whose `agents` entries are directories ("agents: Invalid input") — and a
    refused install would break every routine's bootstrap. No single layout
    satisfies both, so each consumer gets the shape it demands: the
    REPOSITORY keeps the taxonomy folders (the CLI loader recurses — that is
    what routines and local installs read), and the ZIP — consumed only by
    claude.ai — carries the same files flat, with the `agents` manifest key
    dropped so default agents/ discovery applies. Names are unique and
    family-prefixed, so flattening loses nothing; a collision fails the
    build rather than shipping a silent overwrite.
    """
    arcnames, seen = {}, {}
    for rel in (str(e) for e in entries):
        if (rel.startswith("agents/") and rel.endswith(".md")
                and not rel.endswith("README.md")):
            flat = "agents/" + rel.rsplit("/", 1)[-1]
            if flat in seen:
                raise SystemExit(f"agent name collision flattening the zip: "
                                 f"{rel} and {seen[flat]} both become {flat}")
            seen[flat] = rel
            arcnames[rel] = flat
        else:
            arcnames[rel] = rel
    return arcnames


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--walkthrough", action="store_true",
                    help="ALSO build the hierarchical human-tour zip")
    args = ap.parse_args(argv)

    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    entries = list(iter_files())
    fails = check(manifest, entries)
    for f in fails:
        print(f"FAIL {f}", file=sys.stderr)
    if fails:
        return 1

    out_dir = Path(args.out) if args.out else PLUGIN.parent.parent
    out = out_dir / f"dma-insights-{manifest['version']}.zip"
    arcnames = flatten_agents(entries)
    zip_manifest = dict(manifest)
    zip_manifest.pop("agents", None)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in entries:
            arc = arcnames[str(rel)]
            if arc == ".claude-plugin/plugin.json":
                z.writestr(arc, json.dumps(zip_manifest, indent=2) + "\n")
            else:
                z.write(PLUGIN / rel, arc)
    size = out.stat().st_size
    if size > MAX_ZIP_BYTES:
        print(f"FAIL zip is {size} bytes (bound {MAX_ZIP_BYTES})", file=sys.stderr)
        return 1
    print(f"ok  {out}  {len(entries)} files  {size//1024} KiB  "
          f"description {len(manifest['description'])}/{DESCRIPTION_MAX} chars")
    if args.walkthrough:
        wt = build_walkthrough(out.parent, manifest["version"])
        print(f"ok  {wt}  walkthrough (hierarchical, for humans — "
              f"NOT for claude.ai upload)  {wt.stat().st_size//1024} KiB")
    return 0



# ── walkthrough zip: the hierarchy, for humans ───────────────────────────

TEST_THEMES = (
    ("1-gates-and-vetting", ("run_gate", "vet_workbooks", "check_language",
                             "corpus_map", "gate")),
    ("2-drive-and-memory", ("drive_fetch", "client_memory", "memory")),
    ("3-corpus-resilience", ("package_resilience", "package_map",
                             "corpus_search", "evidence_normalize",
                             "agent_run", "survey")),
    ("4-learning-loops", ("subcap_match", "source_yield", "learning",
                          "regression", "feedback")),
)


def _test_theme(name: str) -> str:
    low = name.lower()
    for theme, keys in TEST_THEMES:
        if any(k in low for k in keys):
            return theme
    return "5-plugin-infrastructure"


def build_walkthrough(out_dir: Path, version: str) -> Path:
    """The SAME plugin, laid out for a human tour: agents keep their
    hierarchy (11 folders, subagents beneath their pages), tests are
    grouped by theme, and a TOUR.md at the root explains the shape.
    NOT for claude.ai upload — the upload validator wants the flat shape
    the default build produces; this zip is for walking someone through."""
    out = out_dir / f"dma-insights-{version}-walkthrough.zip"
    entries = [(str(rel), PLUGIN / rel) for rel in iter_files()]
    tour = [
        "# dma-insights — walkthrough layout", "",
        f"Version {version}. This zip mirrors the REPOSITORY hierarchy so a",
        "human can be walked through it; the flat sibling zip is the one",
        "claude.ai upload accepts.", "",
        "## agents/ — the 47-agent roster, hierarchical",
        "- orchestration/  the surface-producer (only submitter), the",
        "  package-vetter, adversarial-verifier, deployed-app-auditor,",
        "  rectifier",
        "- production/<page>/  one folder per dashboard page; the page",
        "  producer beside the per-surface subagents it fans out to",
        "- enrichment/  planner + connector/web specialists + ledger auditor",
        "- checkers/  finding-challenger, page-consolidator, evidence and",
        "  numeric checkers, exclusion-boundary auditor",
        "- qa/  qa-overseer (the learning loop's only writer)",
        "- learning/  learning-grader + learning-testgen (graders carry no",
        "  write tools by construction)", "",
        "## skills/dma-surface-production/ — the production system",
        "- 02-inputs/  1-package (landing table) · 5-corpus-map (source ->",
        "  storyline -> enrichment precedence per surface) · 4-vetting",
        "- 03-pages/  per-page rulebooks",
        "- 05-lifecycle/  routing (incl. Dispatch mode) · surface-map",
        "  (census) · gates · client-memory", "",
        "## scripts/ — the mechanical layer",
        "- run_gate.py  the pre-synthesis gate (G1-G4)",
        "- package_map.py / corpus_search.py / evidence_normalize.py  the",
        "  messy-corpus resolution ladder",
        "- drive_fetch.py / client_memory.py  Drive + per-client memory",
        "- agent_run.py  headless agent dispatch for trigger-fired sessions",
        "- package_survey.py  the measuring instrument (survey/deep/corpus/",
        "  trends)", "",
        "## scripts/tests/ — grouped by theme",
    ]
    theme_counts = {}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, path in entries:
            arc = rel
            parts = rel.split("/")
            if parts[0] == "scripts" and len(parts) > 2 \
                    and parts[1] == "tests" and parts[-1] != "__init__.py":
                theme = _test_theme(parts[-1])
                theme_counts[theme] = theme_counts.get(theme, 0) + 1
                arc = "/".join(parts[:2] + [theme, parts[-1]])
            z.write(path, arc)
        for theme, _ in TEST_THEMES:
            if theme in theme_counts:
                tour.append(f"- {theme}/  {theme_counts[theme]} test files")
        if "5-plugin-infrastructure" in theme_counts:
            tour.append(f"- 5-plugin-infrastructure/  "
                        f"{theme_counts['5-plugin-infrastructure']} test files")
        z.writestr("TOUR.md", "\n".join(tour) + "\n")
    return out


if __name__ == "__main__":
    sys.exit(main())
