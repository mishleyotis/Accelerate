"""The two evidence counts on `subcap_scores`, in one place.

Both are recomputed from `evidence_subcap_links` rather than incremented, so a
link written twice or a run replayed cannot drift them. They were four
copies of the same UPDATE across three modules; the second count would have
been a fifth, sixth and seventh, and the first time one copy was missed the
symptom would be a cell reading THIN on a page while the links behind it were
right — a defect with no error and no log line.

  linked_evidence_count   every link, whatever it points at.
  citable_evidence_count  links a reader can actually open. A link counts
                          when its own row carries a verbatim span, OR when
                          another row for the SAME artefact does — the rule
                          `packages/shared/evidence_merge.py` applies to the
                          served listing, written once more in SQL because a
                          generated column cannot call Python.

                          Both halves matter. The package supplies the CELL
                          LINKS and no spans; a producer registers the span
                          against the same url and no links. Counting only
                          the first half left the drawer showing a quotable
                          citation over a cell still flagged thin — the flag
                          and the page disagreeing about the same evidence,
                          which is worse than either being wrong alone.
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
            AND ((e.excerpt IS NOT NULL AND length(btrim(e.excerpt)) > 0)
                 OR EXISTS (SELECT 1 FROM evidence_index e2
                             WHERE e2.entity_id = e.entity_id
                               AND e2.e_id <> e.e_id
                               AND e2.excerpt IS NOT NULL
                               AND length(btrim(e2.excerpt)) > 0
                               AND e.source_url IS NOT NULL
                               AND e.source_url <> ''
                               AND rtrim(lower(regexp_replace(
                                     e2.source_url, '^https?://', '')), '/')
                                 = rtrim(lower(regexp_replace(
                                     e.source_url, '^https?://', '')), '/'))))
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
