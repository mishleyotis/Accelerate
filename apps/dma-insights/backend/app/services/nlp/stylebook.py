"""L5 — deterministic per-client style variation (the anti-template engine).

The 2026-07-13 stress-test measured the shipped pack's cross-client sentence
reuse directly: masking numbers and entity names, 158 six-word frames in the
exec summary were shared by >=10 of the 94 clients (the Question sentence was
verbatim in 88), the platform story shared 260 frames (many at 94/94), and the
insight WHY shared 50. Grounded is necessary but not sufficient — a narrative
an AE reads next to a colleague's must not be the colleague's narrative with
the nouns swapped.

This module gives every composer the same two primitives:

  ``seeded(*keys)``  — a deterministic ``random.Random`` derived from stable
                       client/surface keys (display_id, platform_id, subcap_id
                       …). Same keys → same choices forever (idempotent packs,
                       reproducible CI); different clients → different draws.
  ``pick(rng, pool)``— draw one realization from a frame pool.

and one policy decision:

  ``scqa_style(...)``— the executive-summary architecture for a client,
                       chosen CONTENT-FIRST (an unresolved consent order pulls
                       toward the risk-led frame; a fresh C-suite seat pulls
                       toward momentum; a genuine above-peer strength unlocks
                       the tension/contrarian frames) with the seeded draw
                       spreading clients that share the same signal profile
                       across the eligible styles.

Style is VARIATION OF FORM ONLY. Facts, scores, citations and the quality
gates (rubric_score, family floor, exec-summary checks) are invariant — a
style may reorder and rephrase, it must never add, soften, or drop a grounded
claim. Every frame pool below is written so each realization carries the same
slots (capability name, score text, citation) and stays inside the pack's
language rules (no internal jargon, no deficit framing, citation-safe).
"""
from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence


def seeded(*keys: object) -> random.Random:
    """Deterministic RNG from stable keys. SHA-256 (not ``hash()``) so draws
    are stable across processes and Python releases."""
    raw = "␟".join(str(k) for k in keys)
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def pick(rng: random.Random, pool: Sequence[str], **slots: object) -> str:
    """Draw one frame from ``pool`` and fill its ``{slot}``s. A pool is never
    empty by contract; slots the frame does not use are ignored."""
    frame = pool[rng.randrange(len(pool))]
    return frame.format(**slots) if slots else frame


def spread(rng: random.Random, eligible: Sequence[str], top: int = 3) -> str:
    """Pick among the first ``top`` eligible options — content ranks the
    candidates, the seeded draw spreads same-profile clients across them."""
    n = min(max(1, top), len(eligible))
    return eligible[rng.randrange(n)]


# ── Executive-summary architecture ──────────────────────────────────────────
# Six architectures. Every one leads with the KEY MESSAGE (the binding
# constraint and the prize/play) — never firmographics, never background.
#   thesis     — declarative: the single highest-leverage move, argued.
#   tension    — the strength/gap contrast carries the story.
#   momentum   — the timing window (new leadership, accelerating trend) leads.
#   risk       — the unresolved regulatory/operational fact sets the stakes.
#   contrarian — opens against the headline number ("the average hides it").
#   decision   — framed as the one choice this cycle, options priced.
SCQA_STYLES = ("thesis", "tension", "momentum", "risk", "contrarian", "decision")


def scqa_style(client_key: str, signals: dict) -> str:
    """The exec-summary architecture for this client.

    ``signals`` (all optional booleans):
      unresolved_issue — an OPEN critical/high issue exists
      new_hire         — a fresh executive seat
      accelerating     — analyst-classified accelerating trajectory
      strength         — a genuine at/above-peer counter-signal exists
      big_uplift       — closing the lead gap is worth >= 0.8 maturity points
    """
    rng = seeded(client_key, "scqa-style")
    ranked: list[str] = []
    if signals.get("unresolved_issue"):
        ranked.append("risk")
    if signals.get("new_hire") or signals.get("accelerating"):
        ranked.append("momentum")
    if signals.get("strength"):
        ranked.extend(("tension", "contrarian"))
    if signals.get("big_uplift"):
        ranked.append("decision")
    ranked.extend(("thesis", "decision", "tension"))
    eligible: list[str] = []
    for s in ranked:
        if s not in eligible:
            eligible.append(s)
    return spread(rng, eligible, top=3)


# ── Shared connective banks (kept small; composers own their frame pools) ──
# Adverbial lead-ins ONLY — each must read grammatically before a full
# clause ("<conn> X holds 1.0/5 …"), so no frame that requires an object.
AND_ALSO = ("Alongside it,", "In the same file,", "Just behind it,",
            "On the same page of the assessment,", "A second front:")
THEREFORE = ("The upshot:", "Net:", "What follows:", "Taken together,",
             "Read together,")
