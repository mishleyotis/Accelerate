#!/usr/bin/env python3
"""CI Gate D — a shared contract the code reads must ship in the image.

THE DEFECT THIS EXISTS FOR, measured 2026-08-14 on the deployed API.

`packages/shared/enrichment_register.json` declares which surfaces depend on an
enrichment source. `apps/api/dma_api/computed.py` reads it at request time to
compute each section's `enrichment_status`. The api Dockerfile copied `dma_api`
and nothing else, so the file was never in the image. The loader's
`except Exception: {}` turned FileNotFoundError into "no surfaces are declared",
and all five enrichment surfaces served without their status.

Every test passed. The unit tests read the file from the repo, where it exists.
The deployed service read it from `/`, where it did not. Nothing anywhere
compared the two.

THE CLASS is wider than one file: any deployable whose code names a
`packages/shared/<file>` and whose build context does not carry it fails the
same way — silently, at runtime, in production only, with a green suite. So the
check is not "is the register staged" but "for every shared file any deployable
READS, does that deployable's build actually SHIP it".

HOW IT CHECKS. For each deployable, find the shared filenames its source names,
then satisfy each one of three ways:
  · the Dockerfile COPYs a directory the deploy script stages it into
  · the deploy script copies it into that build's context
  · the file lives inside the deployable's own tree already
Any shared file a deployable reads and none of those three provide is a
failure — the same failure, waiting.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "packages" / "shared"
DEPLOY = ROOT / "infra" / "deploy.sh"

# The deployables, and the source trees whose code can read a shared file.
DEPLOYABLES = {
    "apps/api": ["apps/api/dma_api"],
    "apps/mcp": ["apps/mcp/dma_mcp", "apps/mcp"],
    "apps/worker": ["apps/worker/dma_worker"],
    "infra/jobs": ["infra/jobs"],
}
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
SKIP_PARTS = {"tests", "test", "__pycache__", "node_modules", ".next"}


def shared_files() -> set:
    if not SHARED.exists():
        return set()
    return {p.name for p in SHARED.iterdir() if p.is_file()}


def _code_lines(text: str, suffix: str):
    """(lineno, line) for lines that are CODE, not commentary.

    Needed because this file's own prose names the shared files it polices, and
    so does every comment explaining why one is staged. A gate that fails on a
    comment gets switched off, so the detector has to read only what runs.
    Crude but one-directional: when in doubt it keeps the line, so a real
    reference is never dropped.
    """
    in_block = False
    in_doc = ""          # the triple-quote that opened the current docstring
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw
        if suffix == ".py":
            # Docstrings are STRINGS, not comments, so `#`-stripping leaves
            # them — and this module's own docstrings name the very files it
            # polices. Every explanation of why a file is staged mentions it.
            if in_doc:
                if in_doc in s:
                    s = s.split(in_doc, 1)[1]
                    in_doc = ""
                else:
                    continue
            for q in ('"""', "'''"):
                while q in s:
                    before, _, rest = s.partition(q)
                    if q in rest:
                        s = before + rest.split(q, 1)[1]
                    else:
                        s, in_doc = before, q
                        break
                if in_doc:
                    break
            s = re.sub(r"#.*$", "", s)
        else:
            if in_block:
                if "*/" in s:
                    in_block = False
                    s = s.split("*/", 1)[1]
                else:
                    continue
            while "/*" in s:
                before, _, rest = s.partition("/*")
                if "*/" in rest:
                    s = before + rest.split("*/", 1)[1]
                else:
                    s, in_block = before, True
                    break
            s = re.sub(r"//.*$", "", s)
        if s.strip():
            yield i, s


def read_references(dirs, names) -> dict:
    """{shared filename: [file:line, …]} for every deployable-source mention."""
    found: dict = {}
    for d in dirs:
        base = ROOT / d
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in CODE_SUFFIXES:
                continue
            if SKIP_PARTS.intersection(path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for lineno, line in _code_lines(text, path.suffix):
                for name in names:
                    if name in line or _imports_module(line, name):
                        found.setdefault(name, []).append(
                            f"{path.relative_to(ROOT)}:{lineno}")
    return found


def _imports_module(line: str, name: str) -> bool:
    """Does this line IMPORT the shared file as a module?

    THE MISS THIS CLOSES. `apps/mcp/dma_mcp/gaps.py` was rewritten to
    `from enrichment_gaps import (...)`. The only place the string
    "enrichment_gaps.py" appeared was a trailing comment, and this gate strips
    comments — correctly, since its own prose names the files it polices. So
    the reference was invisible, the gate passed, the mcp image shipped without
    the module, and the container died on its startup probe. Cloud Run kept
    traffic on the previous revision, so it was a failed deploy rather than an
    outage — by Cloud Run's grace, not by design.

    A python module is imported by its STEM, never its filename, so a gate that
    only looks for filenames cannot see the most common way a shared file is
    used. Matching `import <stem>` and `from <stem> import` closes that.
    """
    if not name.endswith(".py"):
        return False
    stem = re.escape(name[:-3])
    return bool(re.search(rf"^\s*(?:from\s+{stem}\s+import|import\s+{stem})\b",
                          line))


def dockerfile_copies(deployable: str) -> list:
    df = ROOT / deployable / "Dockerfile"
    if not df.exists():
        return []
    out = []
    for line in df.read_text().splitlines():
        s = line.strip()
        if s.upper().startswith("COPY "):
            out.extend(s.split()[1:-1])
    return out


def staged_by_deploy(name: str) -> bool:
    """Does deploy.sh copy this shared file into any build context?"""
    if not DEPLOY.exists():
        return False
    text = DEPLOY.read_text()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        if "cp " in s and name in s:
            return True
    return False


def main() -> int:
    names = shared_files()
    if not names:
        print("Gate D: packages/shared has no files; nothing to check.")
        return 0

    violations, checked = [], 0
    for deployable, dirs in DEPLOYABLES.items():
        refs = read_references(dirs, names)
        if not refs:
            continue
        copies = dockerfile_copies(deployable)
        own_tree = {p.name for p in (ROOT / deployable).rglob("*") if p.is_file()}
        for name, sites in sorted(refs.items()):
            checked += 1
            # 1 · the deployable already carries its own copy
            if name in own_tree:
                continue
            # 2 · deploy.sh stages it into a build context
            if staged_by_deploy(name):
                # …and the Dockerfile must actually COPY the staging dir.
                if deployable == "infra/jobs" or any(
                        c in ("shared", "./shared", ".", "shared/")
                        for c in copies):
                    continue
                violations.append(
                    f"  {deployable}: deploy.sh stages {name!r} but "
                    f"{deployable}/Dockerfile never COPYs the staging "
                    f"directory (COPY lines: {copies or 'none'}).\n"
                    f"      read at {sites[0]}")
                continue
            violations.append(
                f"  {deployable}: reads packages/shared/{name} at "
                f"{sites[0]}\n"
                f"      but nothing puts it in the image — deploy.sh does not "
                f"stage it and the Dockerfile does not copy it.\n"
                f"      At runtime the read fails; if the caller swallows "
                f"that, the service serves as though the contract were empty.")

    if violations:
        print("GATE D FAILED — a shared contract is read but never shipped:\n")
        print("\n\n".join(violations))
        print("\n\nFix by staging it into the build context, the way "
              "corpus_gates.json is staged for the corpus jobs — never by "
              "committing a second copy into the deployable, which drifts "
              "from the one CI checks.")
        return 1
    print(f"Gate D passed: {checked} shared-file reference(s) all ship.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
