/**
 * RequestDmaModal — prototype-strict "Trigger new assessment" wizard, ported
 * 1:1 from the wireframe NewRunModal (04_components_c.js:520-652) using the
 * SAME modal chrome the prototype ships (.modal-mask / .modal / .modal-head /
 * .modal-body / .modal-foot in app.css) — NOT the generic <Modal> wrapper,
 * whose .modal-backdrop/.modal-title chrome rendered visibly different.
 *
 *   Step 1 · Entity details — Client name*, Website* (+Explorium helper),
 *            Subvertical select (SUBVERTICAL_LABEL).
 *   Step 2 · Context & files — context textarea, dashed file drop zone
 *            (file NAMES only — no upload endpoint, so they fold into notes),
 *            "Pass to DMA bot" toggle.
 *   Step 3 · Confirm — read-only summary tile + what-happens-next copy.
 * Head: eyebrow + step title + 1/2/3 step circles + close. Foot: Back /
 * Continue (validation-gated) / Start assessment.
 *
 * Submit → existing useRequestNewRun (name→entity_name, website→entity_domain,
 * notes + file names→notes, urls:[]). No URLs field by design, so the
 * server-side evidence_mode→hybrid trigger is unreachable here (documented).
 * States: closed→null · wizard · submitting · error (in-modal banner) ·
 * success (request_id + Ops-Sheet row + evidence_mode pill).
 */
import { useEffect, useState } from "react";
import { Icon, Pill, Spinner } from "@/components/utils";
import { useRequestNewRun } from "@/lib/queries";
import { SUBVERTICAL_LABEL } from "@/lib/labels";

interface RequestDmaModalProps {
  open: boolean;
  onClose: () => void;
}

interface WizardFile { name: string; size: number }

const EMPTY_FORM = {
  name: "",
  website: "",
  subvertical: "RB",
  notes: "",
  files: [] as WizardFile[],
  passToDmaBot: true,
};

export function RequestDmaModal({ open, onClose }: RequestDmaModalProps): JSX.Element | null {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [success, setSuccess] = useState<{
    request_id: string;
    sheet_row_url: string | null;
    evidence_mode: "public" | "hybrid";
  } | null>(null);

  const mutation = useRequestNewRun();

  useEffect(() => {
    if (open) {
      setStep(1);
      setForm({ ...EMPTY_FORM });
      setSuccess(null);
      mutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Escape closes + body scroll lock while open (the generic Modal did this;
  // replicate since we render the prototype chrome directly).
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") handleClose(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const valid1 = form.name.trim().length > 1 && form.website.trim().length > 3;

  function handleClose() {
    setForm({ ...EMPTY_FORM });
    setStep(1);
    setSuccess(null);
    mutation.reset();
    onClose();
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const fs = Array.from(e.target.files ?? []);
    setForm((f) => ({ ...f, files: [...f.files, ...fs.map((file) => ({ name: file.name, size: file.size }))] }));
    e.target.value = "";
  }
  function removeFile(i: number) {
    setForm((f) => ({ ...f, files: f.files.filter((_, x) => x !== i) }));
  }

  async function submit() {
    const fileNote = form.files.length
      ? `\n\nSupporting files (names only): ${form.files.map((f) => f.name).join(", ")}`
      : "";
    const handoffNote = form.passToDmaBot ? "" : "\n\n[AE flagged: hold for manual queue, do not auto-dispatch]";
    const notes = `${form.notes.trim()}${fileNote}${handoffNote}`.trim();
    const result = await mutation.mutateAsync({
      entity_name: form.name.trim(),
      entity_domain: form.website.trim() || undefined,
      notes: notes || undefined,
      urls: [],
      priority: "normal",
    });
    setSuccess({
      request_id: result.request_id,
      sheet_row_url: result.sheet_row_url,
      evidence_mode: result.evidence_mode,
    });
  }

  const stepTitle = step === 1 ? "Entity details" : step === 2 ? "Context & files" : "Confirm";

  return (
    <div className="modal-mask" onClick={handleClose}>
      <div className="modal" style={{ width: 640 }} role="dialog" aria-modal="true"
           aria-label="Trigger new assessment" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div style={{ flex: 1 }}>
            <div className="eyebrow" style={{ marginBottom: 4 }}>Trigger new assessment</div>
            <div style={{ fontSize: 17, fontWeight: 600, color: "var(--z-dark)" }}>
              {success ? "Request submitted" : stepTitle}
            </div>
          </div>
          {!success ? (
            <div className="row" style={{ gap: 6, marginRight: 8 }}>
              {[1, 2, 3].map((n) => (
                <div key={n} aria-current={step === n ? "step" : undefined} style={{
                  width: 22, height: 22, borderRadius: 11, fontSize: 11, fontWeight: 600,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: step >= n ? "var(--z-teal)" : "var(--z-sep)",
                  color: step >= n ? "#fff" : "var(--z-muted)",
                }}>{n}</div>
              ))}
            </div>
          ) : null}
          <button type="button" className="icon-btn" onClick={handleClose} aria-label="Close">
            <Icon name="x" size={18} />
          </button>
        </div>

        <div className="modal-body">
          {success ? (
            <div className="request-success" role="status">
              <p>Bot accepted the request and returned ID <code>{success.request_id}</code>.</p>
              <p>
                Evidence mode:{" "}
                <Pill tone={success.evidence_mode === "hybrid" ? "teal" : "neutral"}>{success.evidence_mode}</Pill>
              </p>
              {success.sheet_row_url ? (
                <p><a href={success.sheet_row_url} target="_blank" rel="noopener noreferrer">Open the live row in the Ops Sheet ↗</a></p>
              ) : null}
            </div>
          ) : step === 1 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="field-group">
                <label className="inp-label" htmlFor="nr-name">Client name <span style={{ color: "var(--z-below)" }}>*</span></label>
                <input id="nr-name" className="inp" autoFocus placeholder="e.g. Provident Bank"
                       value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
              </div>
              <div className="field-group">
                <label className="inp-label" htmlFor="nr-web">Website <span style={{ color: "var(--z-below)" }}>*</span></label>
                <input id="nr-web" className="inp" placeholder="https://provident.com"
                       value={form.website} onChange={(e) => setForm((f) => ({ ...f, website: e.target.value }))} />
                <div className="inp-help">Used as the primary entity match for Explorium technographic sync.</div>
              </div>
              <div className="field-group">
                <label className="inp-label" htmlFor="nr-sv">Subvertical</label>
                <select id="nr-sv" className="inp" value={form.subvertical}
                        onChange={(e) => setForm((f) => ({ ...f, subvertical: e.target.value }))}>
                  {Object.entries(SUBVERTICAL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
            </div>
          ) : step === 2 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="field-group">
                <label className="inp-label" htmlFor="nr-notes">Additional context (optional)</label>
                <textarea id="nr-notes" className="inp" rows={5} style={{ resize: "vertical" }}
                          placeholder="Anything the DMA bot should know — recent news, pending discovery items, prior conversations…"
                          value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
              </div>
              <div className="field-group">
                <label className="inp-label">Supporting files (optional)</label>
                <label style={{ display: "block", padding: "20px 14px", border: "2px dashed var(--z-sep)", borderRadius: 8, textAlign: "center", cursor: "pointer", background: "var(--z-bg)" }}>
                  <Icon name="download" size={18} />
                  <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--z-dark)", marginTop: 6 }}>Drop files or click to browse</div>
                  <div style={{ fontSize: 10.5, color: "var(--z-muted)", marginTop: 3 }}>10-K · annual reports · prior assessment artifacts · max 50MB each</div>
                  <input type="file" multiple onChange={onFile} style={{ display: "none" }} />
                </label>
                {form.files.length > 0 ? (
                  <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
                    {form.files.map((file, i) => (
                      <div key={`${file.name}-${i}`} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "var(--z-lav)", borderRadius: 6 }}>
                        <Icon name="doc" size={13} />
                        <span style={{ fontSize: 12, flex: 1, minWidth: 0 }} className="txt-trunc">{file.name}</span>
                        <span style={{ fontSize: 10, color: "var(--z-muted)" }}>{(file.size / 1024).toFixed(0)} KB</span>
                        <button type="button" className="icon-btn" style={{ width: 22, height: 22 }} aria-label={`Remove ${file.name}`} onClick={() => removeFile(i)}>
                          <Icon name="x" size={11} />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              <label className="row" style={{ fontSize: 12, padding: "10px 12px", background: "var(--z-ice)", borderRadius: 6, cursor: "pointer" }}>
                <span className={`switch ${form.passToDmaBot ? "on" : ""}`} role="switch" aria-checked={form.passToDmaBot}
                      onClick={() => setForm((f) => ({ ...f, passToDmaBot: !f.passToDmaBot }))} />
                <span>Pass payload to DMA bot site for ingestion</span>
              </label>
            </div>
          ) : (
            <div>
              <div className="card-tile" style={{ padding: 14, marginBottom: 12, background: "var(--z-ice)" }}>
                <div className="row" style={{ marginBottom: 8 }}>
                  <Icon name="check" size={15} style={{ color: "var(--z-mid)" }} />
                  <strong style={{ fontSize: 13 }}>Ready to submit</strong>
                </div>
                <SummaryRow k="Client name" v={form.name} />
                <SummaryRow k="Website" v={form.website} />
                <SummaryRow k="Subvertical" v={SUBVERTICAL_LABEL[form.subvertical] ?? form.subvertical} />
                <SummaryRow k="Files" v={form.files.length === 0 ? "—" : `${form.files.length} attached`} />
                <SummaryRow k="Pass to DMA bot" v={form.passToDmaBot ? "Yes" : "No (manual queue)"} />
                {form.notes ? (
                  <>
                    <div style={{ borderTop: "1px solid var(--z-sep)", margin: "8px 0" }} />
                    <div style={{ fontSize: 11, color: "var(--z-muted)", marginBottom: 4 }}>Notes</div>
                    <div style={{ fontSize: 12, color: "var(--z-body)", lineHeight: 1.5 }}>{form.notes}</div>
                  </>
                ) : null}
              </div>
              <div style={{ fontSize: 12, color: "var(--z-muted)", lineHeight: 1.55 }}>
                On submit, the payload is sent to the DMA bot. The bot will: (1) crawl public sources,
                (2) classify evidence into tiers, (3) score each subcap, (4) generate insight cards,
                (5) post results back to this app. First batch is typically available within ~3 minutes.
              </div>
            </div>
          )}

          {mutation.error ? (
            <div className="request-error" role="alert" style={{ marginTop: 12 }}>{mutation.error.message}</div>
          ) : null}
        </div>

        <div className="modal-foot">
          {success ? (
            <>
              <button type="button" className="btn btn-tertiary" onClick={() => { setSuccess(null); setStep(1); setForm({ ...EMPTY_FORM }); mutation.reset(); }}>New request</button>
              <button type="button" className="btn btn-primary" onClick={handleClose}>Done</button>
            </>
          ) : (
            <>
              {step > 1 ? (
                <button type="button" className="btn btn-tertiary" disabled={mutation.isPending} onClick={() => setStep((s) => (s - 1) as 1 | 2 | 3)}>
                  <Icon name="chevron-l" size={12} /> Back
                </button>
              ) : (
                <button type="button" className="btn btn-tertiary" onClick={handleClose}>Cancel</button>
              )}
              {step < 3 ? (
                <button type="button" className="btn btn-primary" disabled={step === 1 && !valid1} onClick={() => setStep((s) => (s + 1) as 1 | 2 | 3)}>
                  Continue <Icon name="arrow-r" size={12} />
                </button>
              ) : (
                <button type="button" className="btn btn-primary" disabled={mutation.isPending} onClick={submit}>
                  {mutation.isPending ? <><Spinner size={12} /> Submitting…</> : <><Icon name="play" size={12} /> Start assessment</>}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SummaryRow({ k, v }: { k: string; v: string }): JSX.Element {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12 }}>
      <span style={{ color: "var(--z-muted)" }}>{k}</span>
      <span style={{ color: "var(--z-dark)", fontWeight: 500 }} className="txt-trunc">{v}</span>
    </div>
  );
}
