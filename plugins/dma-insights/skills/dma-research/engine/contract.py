#!/usr/bin/env python3
"""The one place the DMA research engine states its own shape.

WHY THIS EXISTS. Two audit findings share a single root. AUD-0062 measured
35 occurrences of the literal `836` and 21 of `17 categories` across skills
that feed an assessment, against a settled taxonomy of 851 cells in 16
categories — and the rule that would have prevented it ("counts are derived
by counting catalogue rows at render time; never write one as a literal in
prose") reached no renderer. AUD-0066 measured two incompatible workbook
shapes both called "the workbook", with nothing able to say which was right.

Both are the same defect: a shape asserted in prose in many places instead of
computed in one. So this module computes the counts from the catalogue and
declares the workbook shape as data. Everything downstream — the substrate,
the validator, the renderers, the drift check — reads from here, and a
disagreement becomes a test failure instead of a document that is quietly
wrong.

Nothing in here is a literal that a catalogue change would falsify. The one
irreducible literals are the four band boundaries and the eleven core column
names, and both are stated once, here, with the reason they cannot move.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# ── locating the catalogue ────────────────────────────────────────────────
#
# The engine ships inside the plugin, and the plugin may be installed far
# from any repo checkout. The catalogue is a repo artefact, so it is looked
# for in the places it can actually be, and its absence is reported as an
# absence — never defaulted to a number that looks like data (invariant 9).

_HERE = Path(__file__).resolve()
_CATALOGUE_NAME = "catalogue_v70_tier.json"


def _candidate_catalogue_paths() -> list[Path]:
    """Every place the catalogue can legitimately be, nearest first.

    A repo checkout wins over the packaged copy, so a catalogue update lands
    without a plugin release; the packaged copy exists so a trigger-fired
    container with no checkout can still count (AUD-0069's lesson: an input a
    headless producer cannot resolve is an input it does not have)."""
    out: list[Path] = []
    env = os.environ.get("DMA_CATALOGUE")
    if env:
        out.append(Path(env))
    for anc in _HERE.parents:                       # a checkout above us
        out.append(anc / "packages" / "shared" / _CATALOGUE_NAME)
    out.append(_HERE.parent / "data" / _CATALOGUE_NAME)   # packaged fallback
    return out


class CatalogueUnavailable(RuntimeError):
    """The catalogue could not be read, so no count can be stated.

    Raised rather than returning a plausible number. A run that cannot count
    its own universe must say so; every finding in the AUD-0062 family began
    with a number that was available when it should not have been."""


@lru_cache(maxsize=1)
def catalogue_path() -> Path:
    for p in _candidate_catalogue_paths():
        if p.is_file():
            return p
    raise CatalogueUnavailable(
        "catalogue_v70_tier.json not found. Looked in: "
        + ", ".join(str(p) for p in _candidate_catalogue_paths())
    )


_CELL_RE = re.compile(r"^(P\d)C(\d+)\.(\d+)(?:\.(.+))?$")


@dataclass(frozen=True)
class Taxonomy:
    """The catalogue, counted. Every field is measured, none is asserted."""
    version: str
    cells: tuple[str, ...]
    pillars: tuple[str, ...]
    categories: tuple[str, ...]
    capabilities: tuple[str, ...]
    universal: tuple[str, ...]
    variants: tuple[str, ...]
    tier: dict

    # The counts the prose used to hardcode. Properties, not stored values,
    # so there is no second place for them to drift to.
    @property
    def n_pillars(self) -> int: return len(self.pillars)

    @property
    def n_categories(self) -> int: return len(self.categories)

    @property
    def n_capabilities(self) -> int: return len(self.capabilities)

    @property
    def n_cells(self) -> int: return len(self.cells)

    @property
    def n_universal(self) -> int: return len(self.universal)

    @property
    def n_variants(self) -> int: return len(self.variants)

    def cells_in(self, grain: str) -> tuple[str, ...]:
        """Every cell under a pillar (P1), category (P1C1) or capability
        (P1C1.1). Prefix matching is done on the parsed id, not the string,
        so P1C1 never swallows P1C10."""
        want = grain.strip()
        out = []
        for c in self.cells:
            m = _CELL_RE.match(c)
            if not m:
                continue
            pillar, cat, cap = m.group(1), f"{m.group(1)}C{m.group(2)}", \
                f"{m.group(1)}C{m.group(2)}.{m.group(3)}"
            if want in (pillar, cat, cap):
                out.append(c)
        return tuple(out)

    def sub_vertical_codes(self) -> tuple[str, ...]:
        """The sub-vertical codes the catalogue actually carries, from its
        own tier labels (T2-CU, T2-RB, …). Never a hand-kept list."""
        codes = {v.split("-", 1)[1] for v in self.tier.values() if "-" in v}
        return tuple(sorted(codes))

    def selected(self, sv: str | None, scope: str) -> tuple[str, ...]:
        """The engagement set for a sub-vertical and scope mode.

        AUD-0077: the archive's binder validated neither argument, so an
        unknown scope selected everything and an unknown sub-vertical
        silently produced a 686-cell generic engagement with exit 0. Both
        are refused here — an upstream classification failure must halt,
        not produce a plausible-looking run."""
        if scope not in SCOPE_MODES:
            raise ValueError(
                f"unknown scope {scope!r}; valid: {', '.join(sorted(SCOPE_MODES))}")
        known = self.sub_vertical_codes()
        if sv is not None and sv not in known:
            raise ValueError(
                f"unknown sub-vertical {sv!r}; the catalogue carries: "
                f"{', '.join(known)}")
        univ = list(self.universal)
        if sv is None:
            overlay: list[str] = []
        else:
            overlay = [c for c in self.variants
                       if self.tier.get(c, "").endswith("-" + sv)]
        if scope == "T1_CORE":
            return tuple(univ)
        if scope == "OVERLAY_ONLY":
            return tuple(overlay)
        # FULL and OFFERING both take the overlay. AUD-0077 also measured the
        # overlay landing ALONGSIDE its base sibling, so an entity was
        # researched twice on near-identical capabilities. An overlay
        # supersedes the base cell it varies, so the base is withdrawn.
        superseded = {self.base_of(c) for c in overlay}
        return tuple([c for c in univ if c not in superseded] + overlay)

    def base_of(self, variant: str) -> str | None:
        """The universal cell a sub-vertical variant supersedes, or None.

        `P1C1.3.CU1` varies the capability `P1C1.3`. The archive derived
        `overlay_of` as the parent CAPABILITY id, which is not a cell, so
        0 of 31 targets resolved and no engine code could use it. Resolved
        here to a cell: the lowest-numbered universal sibling under that
        capability, which is the one the variant replaces.

        None is a real answer, not a failure: 68 of the 165 variants sit
        under a capability with no universal sibling at all. Those are
        ADDITIVE — they supersede nothing, and selecting them alongside the
        universal set is correct. Distinguishing the two is the whole point;
        collapsing them is how AUD-0077's double-research happened."""
        m = _CELL_RE.match(variant)
        if not m or (m.group(4) or "").isdigit():
            return None
        cap = f"{m.group(1)}C{m.group(2)}.{m.group(3)}"
        sibs = [c for c in self.universal if c.rsplit(".", 1)[0] == cap]
        return min(sibs) if sibs else None


SCOPE_MODES = ("T1_CORE", "FULL", "OFFERING", "OVERLAY_ONLY")


@lru_cache(maxsize=1)
def taxonomy() -> Taxonomy:
    raw = json.loads(catalogue_path().read_text())
    tier = raw["tier"]
    cells = tuple(sorted(tier))
    pillars, cats, caps = set(), set(), set()
    universal, variants = [], []
    for c in cells:
        m = _CELL_RE.match(c)
        if not m:
            raise CatalogueUnavailable(f"catalogue holds an unparseable id: {c!r}")
        pillars.add(m.group(1))
        cats.add(f"{m.group(1)}C{m.group(2)}")
        caps.add(f"{m.group(1)}C{m.group(2)}.{m.group(3)}")
        (universal if (m.group(4) or "").isdigit() else variants).append(c)
    declared = raw.get("cells")
    if declared is not None and declared != len(cells):
        raise CatalogueUnavailable(
            f"catalogue declares {declared} cells and holds {len(cells)}")
    return Taxonomy(
        version=raw.get("catalogue_version", "unknown"),
        cells=cells,
        pillars=tuple(sorted(pillars)),
        categories=tuple(sorted(cats)),
        capabilities=tuple(sorted(caps)),
        universal=tuple(universal),
        variants=tuple(variants),
        tier=tier,
    )


# ── maturity bands ────────────────────────────────────────────────────────
#
# Four bands, strict less-than, on the RAW score before display rounding
# (charter invariant 6). A fifth level must not exist in code, enum or prose:
# AUD-0071 found an 85-block rubric built on five, and AUD-0144 found 36
# offering mappings naming one. The resolver has four branches and the tuple
# below is the only place a band word is written, so there is nowhere for a
# fifth to go and a test asserts the file never names one.

BANDS = ("Activating", "Building", "Competing", "Differentiating")
_BAND_MAX = (2.0, 3.0, 4.0)


def band_of(score):
    """The band word for a raw score, or None when there is no score.

    None is not a band and not a colour: a null score renders as no swatch
    (AUD-0049 found a grey swatch painted for null, which reads as a
    measurement that was never taken)."""
    if score is None:
        return None
    s = float(score)
    for word, hi in zip(BANDS, _BAND_MAX):
        if s < hi:
            return word
    return BANDS[3]


# ── the contract-v3 scoring workbook ──────────────────────────────────────
#
# PROVENANCE, stated because it is load-bearing. The eleven core columns are
# the set the deployed parser already reads (apps/worker/tests/
# test_silent_drop_classes.py::_CANON) and the set the archive's validator
# slices (columns 1..11). The working area's anchors — L Dominant_Claim,
# T Triangulation, V Why_It_Matters, W DMA_Impact, AG Retrieved_At — are the
# positions AUD-0011 and AUD-0065 measured in the pinned template. The
# columns BETWEEN those anchors are this repository's declaration, because
# the pinned Drive template is not resolvable from any code path (AUD-0069)
# and a shape nobody can fetch cannot be the authority for one that runs.
#
# `compare_to_workbook()` below exists so that when the pinned template IS
# fetched, the divergence is reported rather than silently absorbed.

CORE_COLUMNS = (
    "SubCap_ID",         # A
    "SubCap_Name",       # B
    "Category",          # C
    "Score",             # D  research leaves this EMPTY; a value here is rule 4
    "Confidence",        # E
    "Evidence_IDs",      # F  E-id list, or the literal NO_EVIDENCE. Never blank.
    "Source_URLs",       # G
    "Evidence_Ceiling",  # H
    "Caps_Applied",      # I
    "Rationale",         # J
    "Proxy_Searched",    # K
)

WORKING_AREA = (
    "Dominant_Claim",              # L  ← anchor
    "Claim_Label",                 # M
    "What_We_Found",               # N
    "Facet_Coverage",              # O
    "DQ_Works",                    # P
    "DQ_Fails",                    # Q
    "DQ_Value",                    # R
    "DQ_Corroborates",             # S
    "Triangulation",               # T  ← anchor
    "Ceiling_Reasoning",           # U
    "Why_It_Matters",              # V  ← anchor
    "DMA_Impact",                  # W  ← anchor
    "DQ_Contradicts",              # X
    "Contradiction_Disposition",   # Y
    "Absence_Claimed",             # Z
    "Proxy_Log",                   # AA
    "Negative_Ladder",             # AB
    "Discovery_Questions",         # AC
    "Challenge_Verdict",           # AD
    "Ceiling_Band",                # AE
    "Uncertainty",                 # AF
    "Retrieved_At",                # AG ← anchor
)

PILLAR_COLUMNS = CORE_COLUMNS + WORKING_AREA

#: Anchors the pinned template fixes by position. Asserted in a test so a
#: reordering of WORKING_AREA cannot slip through unnoticed.
WORKING_AREA_ANCHORS = {
    "L": "Dominant_Claim", "T": "Triangulation", "V": "Why_It_Matters",
    "W": "DMA_Impact", "AG": "Retrieved_At",
}

EVIDENCE_COLUMNS = (
    "E_ID", "Fact_ID", "Source_Name", "Source_URL", "Tier", "ERS",
    "Date_Published", "Recency", "Claim_Type", "Fact_Count", "SubCap_IDs",
    "Excerpt", "Anchor_Quote", "Retrieved_At", "Origin", "Access_Status",
    "Conflict",
)

TIMELINE_COLUMNS = ("Event_Date", "Event", "Signal", "SubCap_IDs", "Evidence_IDs")

#: The technographic register — the research-stage record behind the fourth
#: deliverable (the Technographic Scan). Vocabulary is the CHARTER's, not the
#: prototype's: four layers OPS/CUST/DATA/INFRA (never L2-L5), four statuses
#: with CLAIMED present and required per row.
TECH_REGISTER_COLUMNS = (
    "TS_ID", "Product", "Vendor", "Layer", "Status", "Evidence_Level",
    "Detection_Basis", "Detection_Method", "SubCap_IDs", "Evidence_IDs",
    "Source_URLs", "As_Of",
)
TECH_LAYERS = ("OPS", "CUST", "DATA", "INFRA")
TECH_STATUS = ("CONFIRMED", "INFERRED", "CLAIMED", "ABSENT")
#: How a detection was made — the scan must say, per row.
TECH_METHODS = ("technographic_scan", "public_document", "job_posting",
                "vendor_announcement", "internal_document", "client_stated")

COVERAGE_COLUMNS = (
    "Category_ID", "Selected", "Researched", "Items", "Floor_Pass",
    "Floor_Pass_Pct", "Synthesised", "Verdict",
)

SEARCH_LOG_COLUMNS = (
    "Seq", "Timestamp", "SubCap_ID", "Facet", "Query", "Tool", "Hits",
    "Kept", "Outcome",
)

GATE_LOG_COLUMNS = (
    "Timestamp", "Gate", "Scope", "Verdict", "Detail", "Blocking",
)

#: WHO did each step. AUD-0018 / AUD-0024: the repository solved reviewer
#: independence BY CONSTRUCTION in one agent — `learning-grader` carries no
#: Write/Edit and no connector write tool, so it cannot touch the change it
#: is scoring — and then explicitly inverted it in the research challenge,
#: where the same actor writes a synthesis and its own verdict on that
#: synthesis. A verdict you wrote on your own work is a feeling.
#:
#: Independence is only checkable if authorship is RECORDED, so every write
#: names its actor here and the gate compares them.
PROVENANCE_COLUMNS = ("SubCap_ID", "Step", "Actor", "At", "Detail")

#: The steps whose authorship is load-bearing.
PROVENANCE_STEPS = ("synthesis", "challenge", "repair", "enrichment")

#: The challenge, in full — the verdict on the scoring row is a
#: denormalised copy of the latest row here, and the gate reconciles them.
CHALLENGE_LOG_COLUMNS = (
    "SubCap_ID", "Verdict", "Actor", "Dimensions", "Rationale",
    "Ceiling_Band_Delta", "At",
)

#: A challenge verdict says one of these. AUD-0102: the schema required a
#: `dimensions` object with no required keys, so a ZERO-dimension verdict
#: validated and the whole challenge could be a token.
CHALLENGE_VERDICTS = ("PASS", "FAIL", "NOT_RUN")

#: The dimensions a challenge must actually address. `synthesis_quality` is
#: the one the shipped card silently omitted, and it carries ten
#: sub-conditions — so it is required by name, not by count.
CHALLENGE_DIMENSIONS = (
    "evidence_sufficiency", "claim_label_fit", "facet_coverage",
    "contradiction_handling", "ceiling_reasoning", "recency",
    "synthesis_quality",
)

HANDOFF_LOCK_COLUMNS = ("Key", "Value")

#: The category-grain peer store, which AUD-0042 found had no feeder at all:
#: the pinned workbook removed `Peer_Benchmarks` and the app's missing-tab
#: path recorded nothing, so `peer_scores` is empty for every new run — which
#: also empties ET-09's allow-list, making a legitimate peer who is also a
#: corpus client read as foreign-entity contamination.
#:
#: The column names are the app's own (`workbook_parser._STAT_ALIASES` and
#: the named-peer columns after them), so a workbook this engine writes is
#: readable by the parser that already exists rather than needing a new one.
PEER_BENCHMARK_COLUMNS = (
    "Category_ID", "Category_Name", "Entity_Score", "Peer_Median",
    "Peer_P25", "Peer_P75", "Peer_N", "Peer_Basis", "Source_Cell",
    "Peer_Names", "Peer_Scores", "As_Of",
)

#: What `Peer_Basis` may say. The app serves a five-rung ladder and discloses
#: which rung a figure came from; a figure with no basis cannot be disclosed.
PEER_BASIS = ("table", "recomputed", "inferred", "cannot_estimate")

#: One row per diagnostic question. `Mode_Fit`, `Internal_Sources` and
#: `Public_Sources` come from the Pillar Scoring Toolkit's own columns I/J/K
#: — the toolkit names, per subcap, exactly which internal artefacts and
#: which public artefacts answer its question, which is the highest-value
#: routing information the workbook carries: a researcher told WHAT to look
#: for stops fishing.
DQ_BANK_COLUMNS = ("SubCap_ID", "Order", "Facet", "Probe_Tier", "Question",
                   "Mode_Fit", "Internal_Sources", "Public_Sources",
                   "Weight_Pct")

#: Where the two client-facing reports are WRITTEN, so they can be CURATED.
#:
#: AUD-0052 measured the reports rendered from the JSON plane and never from
#: the workbook — "the report and the register are produced from DIFFERENT
#: SUBSTRATES with no join, so nothing could have caught it", which is the
#: mechanism behind 6 of 21 cited ids not resolving in a delivered report.
#: An agent writes its narrative HERE, beside the evidence it cites, and the
#: renderer curates from the same sheets the gates read.
REPORT_NARRATIVE_COLUMNS = (
    "Report", "Section_ID", "Heading", "Body", "Evidence_IDs", "Kind",
    "Author", "Written_At",
)

#: `Kind` vocabulary for a Report_Narrative row.
NARRATIVE_KINDS = ("section", "insight_card", "recommendation", "finding")

RUN_METADATA_COLUMNS = ("Key", "Value")

#: The Run_Metadata keys the chain depends on. `run_id` and `catalogue_hash`
#: are the two anti-drift anchors: AUD-0010 found both shipping as unresolved
#: template tokens ({{RUN_ID}}, {{CHECKSUM}}), and AUD-0060 found the
#: catalogue-hash lock built nowhere at all.
RUN_METADATA_KEYS = (
    "run_id", "entity_name", "entity_id", "sub_vertical", "scope_mode",
    "catalogue_version", "catalogue_hash", "taxonomy_pillars",
    "taxonomy_categories", "taxonomy_capabilities", "taxonomy_cells",
    "subcaps_selected", "reference_date", "engine_version", "workbook_contract",
    "evidence_mode", "sv_basis", "mode_basis", "lob_census", "kg_checksum",
    "created_at", "last_written_at", "checkpoint",
)

WORKBOOK_CONTRACT = "v3"
ENGINE_VERSION = "5.0.0"

SHEETS = {
    "00_README": ("Key", "Value"),
    "DQ_Bank": DQ_BANK_COLUMNS,
    "P1_Subcap_Scoring": PILLAR_COLUMNS,
    "P2_Subcap_Scoring": PILLAR_COLUMNS,
    "P3_Subcap_Scoring": PILLAR_COLUMNS,
    "P4_Subcap_Scoring": PILLAR_COLUMNS,
    "Evidence_Detail": EVIDENCE_COLUMNS,
    "Entity_Timeline": TIMELINE_COLUMNS,
    "Tech_Register": TECH_REGISTER_COLUMNS,
    "Coverage": COVERAGE_COLUMNS,
    "Search_Log": SEARCH_LOG_COLUMNS,
    "Gate_Log": GATE_LOG_COLUMNS,
    "Report_Narrative": REPORT_NARRATIVE_COLUMNS,
    "Provenance": PROVENANCE_COLUMNS,
    "Challenge_Log": CHALLENGE_LOG_COLUMNS,
    "Handoff_Lock": HANDOFF_LOCK_COLUMNS,
    "Peer_Benchmarks": PEER_BENCHMARK_COLUMNS,
    "Run_Metadata": RUN_METADATA_COLUMNS,
    "REF_Method": ("Key", "Value"),
}

PILLAR_SHEETS = tuple(f"{p}_Subcap_Scoring" for p in ("P1", "P2", "P3", "P4"))

#: Sheets whose absence is rule 1. Every sheet in SHEETS is required — the
#: archive's validator required a set that the pinned template had already
#: retired (AUD-0012, AUD-0061), so the required set and the generated set
#: are now the same object and cannot disagree.
REQUIRED_SHEETS = tuple(SHEETS)

#: The literal the contract forbids in Source_URLs, in any casing (rule 6).
BANNED_URL_PLACEHOLDERS = ("multiple searches", "see report", "various",
                           "n/a", "tbd", "see above")

NO_EVIDENCE = "NO_EVIDENCE"

TIERS = ("T1", "T2", "T3", "T4", "T5", NO_EVIDENCE)
CLAIM_LABELS = ("FACT", "INFERENCE", "HYPOTHESIS", "CEILING_ESTIMATE")
FACETS = ("works", "fails", "value", "contradicts", "corroborates")

#: The AI overlay, measured from the pinned workbook's own DQ_Bank: its
#: question set is "4255 catalogue + 2553 AI overlay" — 851 x 5 facet probes
#: and 851 x 3 overlay questions exactly, so EVERY subcap carries all three.
AI_FACETS = ("ai_deployment", "ai_data", "ai_constraint")
ALL_FACETS = FACETS + AI_FACETS

#: The DQ that seeds the rest: the Pillar Scoring Toolkit's own Diagnostic
#: Question for the subcap (column H), regraded to an open form where the
#: toolkit wrote it closed.
PRIMARY_FACET = "primary"
DQ_FACETS = (PRIMARY_FACET,) + ALL_FACETS

#: How a run gathers evidence. PUBLIC = web only; INTERNAL = client-supplied
#: documents only; HYBRID = both. The mode decides WHICH diagnostic
#: questions are answerable and which are deferred to discovery — it never
#: silently drops one.
ASSESSMENT_MODES = ("PUBLIC", "INTERNAL", "HYBRID")

#: What a DQ's own toolkit row declares about where its answer lives.
#: Measured from Pillar1_Scoring_Toolkit.xlsx (Source Type column): the
#: values shipped are "Both" and "Public Only"; "Internal Only" is the third
#: member the vocabulary admits. Normalised here to a closed enum.
DQ_MODE_FIT = ("PUBLIC", "INTERNAL", "BOTH")

#: mode -> the mode_fit values whose DQs are ANSWERABLE in that mode.
#: Everything else is DEFERRED: emitted as an INT-Q (or PUB-Q) discovery
#: question with the reason, never silently dropped.
MODE_ANSWERABLE = {
    "PUBLIC": ("PUBLIC", "BOTH"),
    "INTERNAL": ("INTERNAL", "BOTH"),
    "HYBRID": ("PUBLIC", "INTERNAL", "BOTH"),
}

#: The evidence-recency ladder. Undated evidence is UNVERIFIED, never
#: current (invariant 9) — so UNVERIFIED is a member here, not an absence.
RECENCY_LADDER = (
    ("CURRENT", 12), ("RECENT", 24), ("DATED", 36), ("LEGACY", 48),
)
RECENCY_ARCHIVAL = "ARCHIVAL"
RECENCY_UNVERIFIED = "UNVERIFIED"


def catalogue_hash() -> str:
    """A stable digest of the catalogue this run is pinned to.

    AUD-0060: the Client Profile asserts "the hash recorded here is written
    into Handoff_Lock; the assessment stage compares against it and refuses
    to score if the catalogue has moved" — and nothing computed a hash. This
    is that hash. It digests the cell ids and their tiers, so a renamed cell
    or a moved sub-vertical changes it and a reformatted file does not."""
    import hashlib
    t = taxonomy()
    payload = "\n".join(f"{c}\t{t.tier[c]}" for c in t.cells)
    return hashlib.sha256(payload.encode()).hexdigest()


def counts() -> dict:
    """Every count the prose used to hardcode, measured.

    Renderers and skills interpolate from here. AUD-0062's rule — "never
    write one as a literal in prose" — is enforceable only if there is a
    call to make instead."""
    t = taxonomy()
    return {
        "catalogue_version": t.version,
        "catalogue_hash": catalogue_hash(),
        "pillars": t.n_pillars,
        "categories": t.n_categories,
        "capabilities": t.n_capabilities,
        "cells": t.n_cells,
        "universal": t.n_universal,
        "sub_vertical_variants": t.n_variants,
        "bands": len(BANDS),
        "sub_verticals": len(t.sub_vertical_codes()),
    }


def compare_to_workbook(path) -> list[str]:
    """Divergences between a real workbook and this contract, as sentences.

    Exists because the pinned template is a Drive document no code path can
    resolve (AUD-0069). When someone does export it, this reports what
    differs instead of a validator silently accepting whichever shape it
    happens to meet."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    out = []
    have = set(wb.sheetnames)
    for name in REQUIRED_SHEETS:
        if name not in have:
            out.append(f"sheet missing: {name}")
    for extra in sorted(have - set(SHEETS)):
        out.append(f"sheet not in contract: {extra}")
    for name, cols in SHEETS.items():
        if name not in have:
            continue
        ws = wb[name]
        row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        got = tuple((c or "").strip() for c in row if c is not None)
        if got != tuple(cols):
            out.append(
                f"{name}: header differs — contract {list(cols)} vs workbook {list(got)}")
    wb.close()
    return out


if __name__ == "__main__":  # a one-line answer to "what is the shape?"
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        epilog="With no --workbook this prints the counts, measured from the "
               "catalogue. With one, it prints how that workbook diverges "
               "from the contract — which is the honest answer when the "
               "pinned template is exported and compared (AUD-0069).")
    ap.add_argument("--workbook", help="compare this workbook to the contract")
    a = ap.parse_args()
    if a.workbook:
        for line in compare_to_workbook(a.workbook) or ["contract: no divergence"]:
            print(line)
        sys.exit(0)
    print(json.dumps(counts(), indent=2))
