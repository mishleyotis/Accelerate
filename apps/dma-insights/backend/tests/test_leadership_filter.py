"""Leadership person-name filter — drops the "Leadership Gaps" absence
statements the DOCX extractor otherwise emits as fake people (leadership is
Clay-enriched, so a clean/empty seed beats polluted rows)."""
from app.services.parsers.dma_package import _is_person_name


def test_valid_person_names() -> None:
    for n in ("Anders M. Tomson", "L. Dale Cole", "Jay Woo", "Kin Lee-Yow",
              "Troy J. Sanderson", "Mary E. Meisner"):
        assert _is_person_name(n), n


def test_rejects_gap_and_header_nonpeople() -> None:
    for n in ("No CDO", "No Chief Digital Officer", "Leadership Gaps",
              "Leadership Alternatives", "Key Leaders", "Executive Team",
              "Vacant", "N/A", "TBD", "Unknown", "No CRM detected",
              "data governance gap", "transformation without a CDO",
              "Smith", "", "  "):
        assert not _is_person_name(n), n
