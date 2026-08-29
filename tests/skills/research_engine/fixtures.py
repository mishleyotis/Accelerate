"""A small real run, built through the engine's own write path.

Small on purpose: 686 seeded rows is the production shape and a slow test.
The scope-mode and catalogue behaviour is covered in test_contract.py; what
these fixtures exercise is the loop."""
from __future__ import annotations

from engine import contract as C
from engine import ledger as L
from engine import runstate

CAT = "P1C1"


def small_selection(n: int = 6) -> list[str]:
    tax = C.taxonomy()
    return list(tax.cells_in(CAT))[:n]


def new_run(tmp_path, *, n: int = 6, run_id: str = "R-TEST-1"):
    return runstate.start(
        run_id=run_id, entity_name="Acme Credit Union", entity_id="acme-cu",
        sub_vertical="CU", scope_mode="T1_CORE", reference_date="2026-08-29",
        root=tmp_path / "run", selected=small_selection(n))


def bank_evidence(wb, subcap, n=3, *, tier="T2", published="2025-06-01"):
    out = []
    for i in range(n):
        out.append(L.append_evidence(
            wb, source_name=f"Annual Report 2025 p{i+1}",
            source_url=f"https://acme.example/ar25#p{i+1}", tier=tier,
            excerpt=("Alkami digital banking went live in Q3 2024 and reached "
                     f"47 percent member adoption within ninety days, restated "
                     f"at {50+i} percent in the 2025 report."),
            subcaps=[subcap], published=published))
    return out


def good_synthesis(subcap: str, eids: list[str]) -> dict:
    cite = " ".join(f"[{e}:F1]" for e in eids[:2])
    return {
        "Dominant_Claim": ("Acme Credit Union runs digital banking on Alkami "
                           "with measured member adoption."),
        "Claim_Label": "FACT",
        "What_We_Found": (
            f"Alkami digital banking went live in Q3 2024 {cite} and the 2025 "
            "annual report restates member adoption at 52 percent, up from 47 "
            "percent at ninety days. The board pack names a quarterly review "
            "cadence owned by the Chief Digital Officer."),
        "Facet_Coverage": "works, value, corroborates",
        "DQ_Works": ("Alkami went live Q3 2024; adoption 47 percent at ninety "
                     "days, 52 percent in 2025."),
        "DQ_Fails": ("NOT_RUN: no delayed or descoped programme surfaced in "
                     "four adversarial queries across 2023-2026."),
        "DQ_Value": ("Adoption is reported to the board quarterly and is tied "
                     "to the 2025 cost-to-serve target."),
        "DQ_Corroborates": ("The 2025 NCUA call report names the same "
                            "digital channel volumes."),
        "DQ_Contradicts": ("NOT_RUN: no enforcement action, complaint or "
                           "abandoned programme found for Acme in 2023-2026."),
        "Triangulation": (f"Two independent sources agree on the launch date "
                          f"and the adoption figure {cite}."),
        "Ceiling_Reasoning": ("Deployment plus measured utilisation supports a "
                             "Competing ceiling, not Differentiating."),
        "Why_It_Matters": ("Adoption at this level changes which channel the "
                           "cost-to-serve programme can lean on in 2026."),
        "DMA_Impact": ("Lifts the digital-channel capability from Building to "
                       "Competing on measured utilisation, not on deployment."),
        "Ceiling_Band": "Competing",
        "Uncertainty": 0.3,
        "Challenge_Verdict": "PASS",
    }
