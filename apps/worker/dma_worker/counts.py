"""The two evidence counts on `subcap_scores`, in one place.

Both are recomputed from `evidence_subcap_links` rather than incremented, so a
link written twice or a run replayed cannot drift them. They were four
copies of the same UPDATE across three modules; the second count would have
been a fifth, sixth and seventh, and the first time one copy was missed the
symptom would be a cell reading THIN on a page while the links behind it were
right — a defect with no error and no log line.

  linked_evidence_count   every link, whatever it points at.
  citable_evidence_count  links whose evidence row carries a verbatim span.
                          `is_thin_evidence` is generated from this: one
                          citable item clears thin (migration 0053).

NULL is reserved for a run the linker never saw. An unlinked cell on a run the
linker DID process is a computed zero, and the difference is the whole reason
the counts are written after the join exists rather than as rows land.
"""
from __future__ import annotations

RECOUNT_SQL = """
UPDATE subcap_scores sc
   SET linked_evidence_count = (
         SELECT count(*) FROM evidence_subcap_links l
          WHERE l.run_id = sc.run_id AND l.subcap_id = sc.subcap_id),
       citable_evidence_count = (
         SELECT count(*)
           FROM evidence_subcap_links l
           JOIN evidence_index e ON e.e_id = l.e_id
          WHERE l.run_id = sc.run_id
            AND l.subcap_id = sc.subcap_id
            AND e.excerpt IS NOT NULL
            AND length(btrim(e.excerpt)) > 0)
"""


def recount_run(cur, run_id) -> int:
    """Recompute both counts for one run. Returns rows touched."""
    cur.execute(RECOUNT_SQL + " WHERE sc.run_id = %s", (run_id,))
    return cur.rowcount


def recount_where(cur, where: str, params: tuple = ()) -> int:
    """Recompute both counts for the rows a caller's own predicate selects.

    Used by the de-duplicator, which knows the affected runs only as a
    sub-select over the pairs it just rewrote.
    """
    cur.execute(RECOUNT_SQL + " WHERE " + where, params)
    return cur.rowcount
