"""Drive crawler — Cloud Run Job (6-hour Cloud Scheduler).

Per plan §①:
  1. Walk `gs://…/dma-assets/` (or Drive folder via API) for
     `{Client Name} - DMA` folders.
  2. List files; skip those we've parsed before (drive_file_id +
     drive_modified_time dedup against import_files).
  3. Classify each file → file_kind.
  4. Dispatch to the appropriate parser:
       evidence_handoff_json → parse_handoff_text
       scoring_workbook      → scoring_workbook.parse
       research_workbook     → research_workbook.parse_research_workbook
       assessment_report     → assessment_report.parse_report_paragraphs
       client_profile        → DOCX section parser (extract focus_areas)
       issue_register        → workbook parser
       supplementary         → store metadata, no parse
  5. Resolve / create the entity from the folder name.
  6. UPSERT subcap_scores / evidence_index / insight_cards /
     recommendations via the same paths as `/ingest/assessment`.

Live IO (Drive v3 API + GCS) lands in stage 5 finalize alongside Cloud
Scheduler wiring; the dispatch logic in `./dispatch.py` is pure and
tested today.
"""
__all__ = ["dispatch", "main"]
