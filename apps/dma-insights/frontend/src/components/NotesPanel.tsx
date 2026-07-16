/**
 * NotesPanel — the AE-notes segment for drillable rec cards / roadmap
 * items (prototype InsightModal "annotations" tab pattern, extended
 * with the recalibration hook).
 *
 * Render-state matrix:
 *   - customer audience        → parent must not mount (internal only)
 *   - loading                  → spinner row
 *   - no notes                 → "No notes yet." + add form
 *   - notes                    → prototype-style rows (author initials,
 *                                role/status badges, when, body, SF opp)
 *   - note.recalibrate         → assessment chip: SIMULATED (validated
 *                                simulation available — expandable),
 *                                PENDING (Gemini unavailable at write
 *                                time), FAILED (validation rejected —
 *                                honest, nothing rendered as truth),
 *                                REVIEWED (admin signed off)
 *
 * Recalibration copy is explicit that nothing changes automatically:
 * the simulation is stored for admin review with full provenance.
 */
import { useState } from "react";
import { EmptyState, Spinner } from "@/components/utils";
import {
  authorInitials,
  useCreateNote,
  useEntityNotes,
  useNoteAssessment,
  type AeNote,
  type NoteStatus,
  type NoteTargetKind,
} from "@/lib/notes";
import { useEffectiveRole } from "@/store/auth";

interface NotesPanelProps {
  displayId: string;
  targetKind: NoteTargetKind;
  targetId: string;
}

const STATUS_TONE: Record<string, string> = {
  ACTIONED: "b-above",
  PENDING: "b-org",
  SUPERSEDED: "b-muted",
};

const ASSESSMENT_LABEL: Record<string, string> = {
  SIMULATED: "Impact simulated · awaiting admin review",
  PENDING: "Recalibration queued · simulation pending",
  FAILED: "Simulation rejected by validators",
  REVIEWED: "Recalibration reviewed by admin",
};

export function NotesPanel({ displayId, targetKind, targetId }: NotesPanelProps): JSX.Element {
  const role = useEffectiveRole();
  const notesQ = useEntityNotes(displayId, targetKind, targetId);
  const createNote = useCreateNote(displayId);

  const [body, setBody] = useState("");
  const [status, setStatus] = useState<NoteStatus>("PENDING");
  const [sfOppId, setSfOppId] = useState("");
  const [recalibrate, setRecalibrate] = useState(false);

  const canWrite = role !== "CUSTOMER";
  const notes = notesQ.data?.items ?? [];

  const save = (): void => {
    if (!body.trim()) return;
    createNote.mutate(
      {
        target_kind: targetKind,
        target_id: targetId,
        body: body.trim(),
        status,
        sf_opp_id: sfOppId.trim() || null,
        recalibrate,
      },
      {
        onSuccess: () => {
          setBody("");
          setSfOppId("");
          setRecalibrate(false);
          setStatus("PENDING");
        },
      },
    );
  };

  return (
    <div data-testid="ae-notes-panel">
      {notesQ.isLoading ? (
        <div className="page-loading"><Spinner /> Loading notes…</div>
      ) : notes.length === 0 ? (
        <p className="muted" style={{ marginBottom: 12, fontSize: 12 }}>
          No notes yet.
        </p>
      ) : (
        notes.map((n) => <NoteRow key={n.id} note={n} />)
      )}

      {canWrite ? (
        <div className="field-group" style={{ marginTop: 14 }}>
          <label className="inp-label" htmlFor="ae-note-body">Add a note</label>
          <textarea
            id="ae-note-body"
            className="inp"
            rows={4}
            placeholder="Discussed with Delivery Lead before the call…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: "wrap" }}>
            <select
              className="inp"
              style={{ maxWidth: 180 }}
              aria-label="Note status"
              value={status}
              onChange={(e) => setStatus(e.target.value as NoteStatus)}
            >
              <option>ACTIONED</option>
              <option>PENDING</option>
              <option>SUPERSEDED</option>
            </select>
            <input
              className="inp"
              style={{ maxWidth: 220 }}
              placeholder="Salesforce opp ID (optional)"
              value={sfOppId}
              onChange={(e) => setSfOppId(e.target.value)}
            />
            <span className="spacer" />
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!body.trim() || createNote.isPending}
              onClick={save}
            >
              {createNote.isPending ? "Saving…" : "Save note"}
            </button>
          </div>
          <label
            className="row"
            style={{ gap: 6, marginTop: 8, fontSize: 12, cursor: "pointer" }}
          >
            <input
              type="checkbox"
              checked={recalibrate}
              onChange={(e) => setRecalibrate(e.target.checked)}
            />
            <span>
              Flag for recalibration — simulate how this intelligence would
              change findings/scores (admin reviews before anything changes)
            </span>
          </label>
          {createNote.isError ? (
            <p style={{ color: "var(--z-below)", fontSize: 12, marginTop: 6 }}>
              Couldn't save note: {createNote.error.message}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function NoteRow({ note }: { note: AeNote }): JSX.Element {
  const when = new Date(note.created_at).toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });
  return (
    <div
      style={{ background: "var(--z-lav)", borderRadius: 8, padding: 14, marginBottom: 10 }}
      data-testid="ae-note-row"
    >
      <div className="row" style={{ gap: 8, marginBottom: 6, fontSize: 12, flexWrap: "wrap" }}>
        <div className="sb-avatar" style={{ width: 22, height: 22, fontSize: 9 }}>
          {authorInitials(note.author_email)}
        </div>
        <strong>{note.author_email}</strong>
        <span className="b b-teal">{note.author_role}</span>
        <span className={`b ${STATUS_TONE[note.status] ?? "b-muted"}`}>{note.status}</span>
        {note.sf_opp_id ? <span className="chip">{note.sf_opp_id}</span> : null}
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--z-muted)" }}>{when}</span>
      </div>
      <div style={{ fontSize: 13, color: "var(--z-body)", lineHeight: 1.55 }}>{note.body}</div>
      {note.recalibrate ? <RecalibrationChip note={note} /> : null}
    </div>
  );
}

function RecalibrationChip({ note }: { note: AeNote }): JSX.Element {
  const [open, setOpen] = useState(false);
  const st = note.assessment_status ?? "PENDING";
  const label = ASSESSMENT_LABEL[st] ?? `Recalibration · ${st}`;
  const canExpand = st === "SIMULATED" || st === "REVIEWED";
  return (
    <div style={{ marginTop: 8 }}>
      <button
        type="button"
        className="chip purple"
        style={{ cursor: canExpand ? "pointer" : "default", border: 0 }}
        onClick={canExpand ? () => setOpen((o) => !o) : undefined}
        data-testid="recalibration-chip"
      >
        ↺ {label}{canExpand ? (open ? " · hide" : " · view") : ""}
      </button>
      {open && canExpand ? <AssessmentBody noteId={note.id} /> : null}
    </div>
  );
}

function AssessmentBody({ noteId }: { noteId: string }): JSX.Element {
  const q = useNoteAssessment(noteId);
  if (q.isLoading) {
    return <div className="page-loading" style={{ padding: 8 }}><Spinner /></div>;
  }
  if (q.error || !q.data) {
    return (
      <EmptyState
        title="No simulation stored"
        body="The impact assessment hasn't run for this note yet."
      />
    );
  }
  const a = q.data;
  if (!a.validators_passed || !a.assessment_md) {
    return (
      <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        The simulation did not pass validation
        {a.failure_reason ? ` (${a.failure_reason})` : ""} — nothing is shown
        rather than unverified output.
      </p>
    );
  }
  return (
    <div
      style={{
        marginTop: 8, padding: "10px 12px", background: "var(--z-bg)",
        borderLeft: "3px solid var(--z-teal)", borderRadius: 6,
        fontSize: 12, lineHeight: 1.6, whiteSpace: "pre-wrap",
      }}
      data-testid="assessment-md"
    >
      {a.assessment_md}
      <div style={{ marginTop: 8, fontSize: 10.5, color: "var(--z-muted)" }}>
        Model {a.model ?? "n/a"} · grounded on{" "}
        {a.grounding_evidence_ids.length
          ? a.grounding_evidence_ids.join(", ")
          : "no evidence rows"}{" "}
        · {new Date(a.created_at).toLocaleString()}
      </div>
    </div>
  );
}
