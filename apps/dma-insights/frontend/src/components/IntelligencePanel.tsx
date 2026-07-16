/**
 * IntelligencePanel — live-streaming AI surface (right rail).
 *
 * 1:1 with the wireframe (04_components_c.js IntelligencePanel):
 *   - CLOSED → the vertical "✦ INTELLIGENCE" rail (`.ip-tab`) fixed to
 *     the right edge of every authed page. QA audit 2026-06-11:
 *     production shipped the panel but never the rail, so the
 *     5-surface panel was unreachable anywhere in the app.
 *   - OPEN → `aside.ip` with the purple header (✦ + title/sub), the
 *     streamed narrative body, Copy / Regenerate / Deeper·Pro actions,
 *     starter questions per surface, the "Ask anything…" input, and
 *     👍/👎 feedback on every grounded answer.
 *
 * Data paths (all real — no canned strings):
 *   - Surface narrative: SSE /api/v1/sse/intelligence/{surface}/{ref}
 *     (`event: token` concatenation; `done` carries cited E-IDs;
 *     `fallback` swaps in the server-side deterministic body — read
 *     from `text` OR `served_text` — plus `flags` + optional
 *     `cited_evidence_ids`).
 *   - Ask / starters / Deeper·Pro: POST /api/v1/rag/answer (grounded,
 *     validated, synthesis-cache gated server-side). The response
 *     contract is schemas/chat.py RagAnswerResponse — the answer body
 *     is `answer_markdown` (NOT answer_md/answer — reading the wrong
 *     key was the 2026-06 "chat always says No answer returned" bug).
 *   - Chat persistence: `session_id` from the first answer is kept
 *     (sessionStorage, keyed per surface:ref) and sent on subsequent
 *     asks; prior turns hydrate from GET /api/v1/chat/sessions[/{id}]
 *     on panel open.
 *   - Feedback: POST /api/v1/chat/messages/{id}/feedback {rating}.
 *   - why_now surface: the WhyNowSignals accordion renders the deep
 *     trigger-signal fields from the entity overview's
 *     `why_now_signals` (fields render defensively — partially-absent
 *     data until the D1 derivation lands is expected).
 *
 * Render-state matrix:
 *   1. closed                  → `.ip-tab` rail (onOpen)
 *   2. opening, no token yet   → spinner + surface label
 *   3. tokens arriving         → live text + `.ip-cursor`
 *   4. done                    → text + Copy/Regenerate/Deeper + chips
 *   5. fallback                → deterministic body + banner whose copy
 *                                reflects the actual flags (vertex_error
 *                                vs validator vs context_error)
 *   6. socket dropped + retry  → "Reconnecting…" footer note (wired to
 *                                the SSE `__reconnecting`/`reconnect`/
 *                                `error` events; `stream_idle` shows an
 *                                idle note)
 */
import { useEffect, useRef, useState } from "react";
import { subscribeSSE } from "@/lib/sse";
import { apiGet, apiPost } from "@/lib/api";
import { useEntityOverview } from "@/lib/queries";
import { Icon, Spinner } from "@/components/utils";
import { useUiStore } from "@/store/ui";

interface IntelligencePanelProps {
  open: boolean;
  /** Renders the collapsed `.ip-tab` rail when closed. Omit (legacy
   *  embedded usages) and the closed state renders nothing. */
  onOpen?: () => void;
  onClose: () => void;
  surface: string;        // 'subcap_narrative' | 'why_now' | …
  ref_: string;           // e.g. subcap_id or run_id — used in the channel name
  title?: string;
  /**
   * Called when the user clicks a cited E-ID chip. Parent should open
   * the EvidenceDrawer scoped to this evidence row. Optional: if not
   * provided the chip falls back to a `?drawer=evidence&e=<eid>`
   * URL-state mutation via the hash router so deep-linkable.
   */
  onEvidenceClick?: (eid: string) => void;
}

type Phase = "opening" | "streaming" | "done" | "fallback";

interface CitationChip {
  e_id: string;
  source_name?: string | null;
  excerpt?: string | null;
  kind?: "evidence" | "section";
}

/** POST /api/v1/rag/answer response — typed against the backend
 *  contract (schemas/chat.py RagAnswerResponse). */
interface RagAnswerBody {
  session_id?: string;
  message_id?: string;
  answer_markdown?: string;
  cited_evidence_ids?: string[];
  citations?: CitationChip[];
  validators_passed?: boolean;
  fallback_used?: boolean;
  stale_disclaimer?: string;
}

interface ChatTurn {
  role: "user" | "ai";
  text: string;
  pending?: boolean;
  /** chat_messages row id for the assistant turn — feedback target. */
  messageId?: string;
  citations?: CitationChip[];
  citedEvidenceIds?: string[];
  staleDisclaimer?: string;
  fallbackUsed?: boolean;
  feedback?: 1 | -1;
}

/** Surface → header copy (wireframe surfaceMessages, condensed). */
function surfaceHead(surface: string, title?: string): { title: string; sub: string } {
  switch (surface) {
    case "why_now":
      return { title: title ?? "Why now", sub: "Timing signals · grounded on run evidence" };
    case "subcap_narrative":
      return { title: title ?? "Subcap rationale", sub: "Score driver analysis" };
    case "platform_story":
      return { title: title ?? "Platform story", sub: "Conversation-ready narrative" };
    case "insight_explanation":
      return { title: title ?? "Insight explanation", sub: "Why this card exists" };
    case "meeting_prep":
      return { title: title ?? "Meeting prep", sub: "Pre-call brief" };
    case "focus_area":
      return { title: title ?? "Focus area synthesis", sub: "Strategic priority" };
    default:
      return { title: title ?? "Intelligence", sub: "Grounded on this entity's evidence" };
  }
}

/** Starter questions per surface — verbatim from the wireframe
 *  (04_components_c.js starterQuestions incl. the focus_area set and
 *  the aligned default copy). */
function starterQuestions(surface: string): string[] {
  switch (surface) {
    case "why_now":
      return [
        "What's the single most timely platform conversation?",
        "Which evidence is strongest for the integration window?",
        "Where will this entity be in 9 months without intervention?",
      ];
    case "subcap_narrative":
      return [
        "What pulled this score down?",
        "Which platforms would close the gap fastest?",
        "Show me peer benchmarks for this subcap.",
      ];
    case "platform_story":
      return [
        "What are the readiness gaps blocking this platform?",
        "Which insight cards link to this platform?",
        "Give me a 30-second pitch I can use in the next meeting.",
      ];
    case "focus_area":
      return [
        "Which subcaps move the most if we close this focus area?",
        "What's the customer impact, not the technical impact?",
        "Show me peers that closed this focus area in the last 18 months.",
      ];
    default:
      return [
        "Summarise this entity in 30 seconds.",
        "What is the most-asked question on a first call here?",
        "What's our differentiation against the incumbent?",
      ];
  }
}

/** Amber-banner copy keyed to the ACTUAL fallback flags (pre-fix the
 *  banner always claimed "failed grounding validation" even when the
 *  real reason was a Vertex outage). */
function fallbackBannerCopy(flags: Record<string, unknown> | null): string {
  if (!flags || Object.keys(flags).length === 0) {
    return "Fallback served — showing the deterministic template instead.";
  }
  if (flags.vertex_error) {
    return "Gemini unavailable — showing the grounded summary below.";
  }
  if (flags.context_error) {
    return "Insight unavailable — the grounding data for this surface could not be loaded.";
  }
  if (flags.unsupported_surface) {
    return "This surface isn't supported by the intelligence service yet.";
  }
  // Remaining flag families are the grounding validator's
  // (fabricated_e_ids / fabricated_subcap_ids / citation_set_mismatch …).
  return "Withheld — grounding validation failed.";
}

function sessionStorageKey(surface: string, ref: string): string {
  return `dma:ip-chat-session:${surface}:${ref}`;
}

function readStoredSession(surface: string, ref: string): string | null {
  try {
    return window.sessionStorage.getItem(sessionStorageKey(surface, ref));
  } catch {
    return null;
  }
}

function writeStoredSession(surface: string, ref: string, sid: string | null): void {
  try {
    if (sid) window.sessionStorage.setItem(sessionStorageKey(surface, ref), sid);
    else window.sessionStorage.removeItem(sessionStorageKey(surface, ref));
  } catch {
    /* storage unavailable — session persists in-memory only */
  }
}

/** Minimal shapes for the chat-session hydration endpoints
 *  (app/routers/chat.py GET /sessions + GET /sessions/{id}). */
interface ChatSessionSummaryT {
  id: string;
  page_context?: { route?: string } & Record<string, unknown>;
}
interface ChatSessionDetailT {
  id: string;
  messages?: Array<{
    id: string;
    role: string;
    content_markdown: string;
    cited_evidence_ids?: string[];
  }>;
}

function currentRoutePath(): string {
  const hash = window.location.hash.replace(/^#/, "") || "/";
  return hash.split("?")[0] || "/";
}

const str = (v: unknown): string | null =>
  typeof v === "string" && v.trim() ? v : typeof v === "number" ? String(v) : null;

/** WhyNowSignals accordion — prototype 04_components_c.js WhyNowSignals
 *  ported onto the light `.ip` theme. Every deep field renders
 *  defensively (label/category/strength/window/confidence/claim/detail/
 *  metric/peer_context/play/risk/evidence/timeline/impact) — the D1
 *  derivation may leave any of them absent. */
export function WhyNowSignals({
  signals, onEvidence,
}: {
  signals: Array<Record<string, unknown>>;
  onEvidence: (eid: string) => void;
}): JSX.Element | null {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  if (!signals.length) return null;

  const CAT: Record<string, { icon: string; color: string }> = {
    core_migration: { icon: "refresh", color: "var(--z-teal)" },
    leadership: { icon: "users", color: "var(--z-dpur)" },
    hiring: { icon: "users", color: "var(--z-mid)" },
    regulatory: { icon: "lock", color: "var(--z-org)" },
    market: { icon: "stack", color: "var(--z-mid)" },
  };
  const STR: Record<string, string> = {
    STRONG: "b-teal", LEADING: "b-purple", SUPPORTING: "b-muted",
  };

  return (
    <div
      className="ip-whynow-signals"
      style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--ph0-bd)" }}
    >
      <div
        style={{
          fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em",
          color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 8,
        }}
      >
        Trigger signals · click to drill in
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {signals.map((s, i) => {
          const label = str(s.label) ?? str(s.title) ?? `Signal ${i + 1}`;
          const category = str(s.category) ?? "market";
          const strength = str(s.strength);
          const cat = CAT[category] ?? CAT.market;
          const isOpen = openIdx === i;
          const timeline = (typeof s.timeline === "object" && s.timeline !== null
            ? s.timeline
            : null) as Record<string, unknown> | null;
          const evidence = Array.isArray(s.evidence)
            ? (s.evidence as unknown[]).filter((e): e is string => typeof e === "string")
            : Array.isArray(s.evidence_e_ids)
              ? (s.evidence_e_ids as unknown[]).filter((e): e is string => typeof e === "string")
              : [];
          return (
            <div
              key={i}
              className="wn-signal"
              style={{
                border: "1px solid var(--z-sep)", borderRadius: 8,
                overflow: "hidden", background: "#fff",
              }}
            >
              <button
                type="button"
                onClick={() => setOpenIdx((o) => (o === i ? null : i))}
                style={{
                  width: "100%", display: "flex", alignItems: "center", gap: 8,
                  padding: "9px 10px", background: "none", border: 0,
                  cursor: "pointer", textAlign: "left",
                }}
                aria-expanded={isOpen}
              >
                <span
                  style={{
                    width: 22, height: 22, borderRadius: 6, background: cat.color,
                    color: "#fff", display: "flex", alignItems: "center",
                    justifyContent: "center", flexShrink: 0,
                  }}
                >
                  <Icon name={cat.icon} size={12} />
                </span>
                <span
                  className="txt-fit-1"
                  style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 600, color: "var(--z-dark)" }}
                >
                  {label}
                </span>
                {strength ? <span className={`b ${STR[strength] ?? "b-muted"}`}>{strength}</span> : null}
                <Icon name={isOpen ? "chevron-u" : "chevron-d"} size={13} />
              </button>
              {isOpen ? (
                <div style={{ padding: "0 10px 10px", fontSize: 12, lineHeight: 1.6, color: "var(--z-body)" }}>
                  {(str(s.confidence) || str(s.claim)) ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap", marginBottom: 8 }}>
                      {str(s.confidence) ? <span className="b b-muted">{str(s.confidence)} confidence</span> : null}
                      {str(s.claim) ? <span className="b b-muted">{str(s.claim)}</span> : null}
                    </div>
                  ) : null}
                  {str(s.metric) ? (
                    <div
                      className="f-mono"
                      style={{
                        background: "var(--z-ice, rgba(39,187,175,.06))",
                        border: "1px solid var(--z-sep)", borderRadius: 6,
                        padding: "6px 9px", marginBottom: 8, fontSize: 11.5,
                      }}
                    >
                      {str(s.metric)}
                    </div>
                  ) : null}
                  {str(s.detail) ? <div style={{ marginBottom: 8 }}>{str(s.detail)}</div> : null}
                  {str(s.peer_context) ? (
                    <div style={{ marginBottom: 8 }}>
                      <span
                        style={{
                          fontSize: 9.5, fontWeight: 700, letterSpacing: ".08em",
                          color: "var(--z-muted)", textTransform: "uppercase",
                        }}
                      >
                        Peer context ·{" "}
                      </span>
                      <span style={{ fontSize: 11.5 }}>{str(s.peer_context)}</span>
                    </div>
                  ) : null}
                  {timeline && (str(timeline.date) || str(timeline.event)) ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--z-muted)", marginBottom: 8 }}>
                      <Icon name="timeline" size={11} />
                      {str(timeline.date) ? <span className="f-mono">{str(timeline.date)}</span> : null}
                      {str(timeline.event) ? <span>· {str(timeline.event)}</span> : null}
                    </div>
                  ) : null}
                  {str(s.play) ? (
                    <div
                      style={{
                        background: "rgba(39,187,175,.12)", borderLeft: "2px solid var(--z-teal)",
                        borderRadius: 4, padding: "7px 9px", fontSize: 11.5, marginBottom: 6,
                      }}
                    >
                      <strong style={{ color: "var(--z-teal)" }}>Play · </strong>
                      {str(s.play)}
                    </div>
                  ) : null}
                  {str(s.impact) ? (
                    <div
                      style={{
                        background: "rgba(39,187,175,.12)", borderLeft: "2px solid var(--z-teal)",
                        borderRadius: 4, padding: "7px 9px", fontSize: 11.5, marginBottom: 6,
                      }}
                    >
                      <strong style={{ color: "var(--z-teal)" }}>So what · </strong>
                      {str(s.impact)}
                    </div>
                  ) : null}
                  {str(s.risk) ? (
                    <div
                      style={{
                        background: "rgba(254,151,50,.12)", borderLeft: "2px solid var(--z-org)",
                        borderRadius: 4, padding: "7px 9px", fontSize: 11.5, marginBottom: 8,
                      }}
                    >
                      <strong style={{ color: "var(--z-org)" }}>Risk if ignored · </strong>
                      {str(s.risk)}
                    </div>
                  ) : null}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 10, color: "var(--z-muted)", textTransform: "uppercase", letterSpacing: ".08em" }}>
                      Evidence
                    </span>
                    {evidence.length > 0 ? (
                      evidence.map((eid) => (
                        <button
                          key={eid}
                          type="button"
                          className="evidence-chip"
                          onClick={() => onEvidence(eid)}
                          aria-label={`Open evidence ${eid}`}
                        >
                          {eid}
                        </button>
                      ))
                    ) : (
                      <span style={{ fontSize: 11, color: "var(--z-muted)" }}>
                        Inferred — confirm in discovery
                      </span>
                    )}
                    <span style={{ flex: 1 }} />
                    {str(s.window) ? (
                      <span className="b" style={{ background: cat.color, color: "#fff" }}>
                        {str(s.window)}
                      </span>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function IntelligencePanel({
  open, onOpen, onClose, surface, ref_, title, onEvidenceClick,
}: IntelligencePanelProps) {
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>("opening");
  const [citedEvidenceIds, setCitedEvidenceIds] = useState<string[]>([]);
  const [fallbackFlags, setFallbackFlags] = useState<Record<string, unknown> | null>(null);
  // null = healthy; otherwise the footer note ("Reconnecting…" / idle).
  const [connNote, setConnNote] = useState<string | null>(null);
  const [chat, setChat] = useState<ChatTurn[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatPending, setChatPending] = useState(false);
  const [streamNonce, setStreamNonce] = useState(0);
  const subRef = useRef<ReturnType<typeof subscribeSSE> | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const chatSessionRef = useRef<string | null>(null);
  const pushToast = useUiStore((s) => s.pushToast);

  // why_now deep signals: the ref for that surface is the display_id
  // (intelligence_builder ref contract) — fetch the overview so the
  // WhyNowSignals accordion can render the trigger-signal drilldown.
  const whyNowDisplayId =
    open && surface === "why_now" && ref_ ? ref_.split(":")[0] || null : null;
  const overviewQ = useEntityOverview(whyNowDisplayId);
  const whyNowSignals = whyNowDisplayId
    ? overviewQ.data?.why_now_signals ?? []
    : [];

  useEffect(() => {
    if (!open) return;
    // Don't open the SSE stream until we have a real ref. Without this
    // guard the panel mounts with empty ref on every page load and
    // streams /api/v1/sse/intelligence/{surface}/ → 404 forever (the
    // panel sits stuck on "Opening stream…").
    if (!ref_) {
      // No context yet (e.g. on a page that doesn't bind a ref) — stay
      // in the "opening" placeholder until a real ref arrives.
      return;
    }
    setText("");
    setPhase("opening");
    setCitedEvidenceIds([]);
    setFallbackFlags(null);
    setConnNote(null);

    const url = `/api/v1/sse/intelligence/${surface}/${encodeURIComponent(ref_)}`;
    const sub = subscribeSSE(url, {
      hello: () => setConnNote(null),
      token: (data) => {
        try {
          const parsed = JSON.parse(data) as { text?: string };
          if (parsed.text) {
            setPhase("streaming");
            setConnNote(null);
            setText((t) => t + parsed.text);
          }
        } catch {
          /* malformed token frame — skip */
        }
      },
      done: (data) => {
        setPhase("done");
        setConnNote(null);
        try {
          const parsed = JSON.parse(data) as { cited_evidence_ids?: string[] };
          setCitedEvidenceIds(parsed.cited_evidence_ids ?? []);
        } catch {
          setCitedEvidenceIds([]);
        }
        // The narrative is complete — close the subscription so the
        // auto-reconnect doesn't re-trigger the builder (duplicate
        // Vertex spend + duplicated text).
        subRef.current?.close();
      },
      fallback: (data) => {
        setPhase("fallback");
        setConnNote(null);
        try {
          const parsed = JSON.parse(data) as {
            text?: string;
            served_text?: string;
            flags?: Record<string, unknown>;
            cited_evidence_ids?: string[];
          };
          // The builder publishes the deterministic body under BOTH
          // `text` (forward contract) and `served_text` (historical);
          // read either so the amber banner never shows an empty body.
          const body = parsed.text ?? parsed.served_text;
          if (body) setText(body);
          setFallbackFlags(parsed.flags ?? null);
          setCitedEvidenceIds(parsed.cited_evidence_ids ?? []);
        } catch {
          setFallbackFlags(null);
        }
        subRef.current?.close();
      },
      // Server-side control events (app/routers/sse.py).
      reconnect: () => setConnNote("Reconnecting…"),
      error: () => setConnNote("Reconnecting…"),
      stream_idle: () => setConnNote("Stream idle — still waiting for content…"),
      // Synthetic wrapper events (lib/sse.ts).
      __reconnecting: () => setConnNote("Reconnecting…"),
      __connected: () => setConnNote(null),
      message: () => undefined,
    });
    subRef.current = sub;
    return () => {
      sub.close();
      subRef.current = null;
    };
  }, [open, surface, ref_, streamNonce]);

  // Keep the chat tail in view as answers stream in.
  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [chat, chatPending]);

  // Reset + hydrate the side-chat when the surface context changes.
  // Session round-trip: a stored session_id (per surface:ref) resumes
  // the conversation across panel closes and page reloads; without one
  // we fall back to the most recent server-side session for this route.
  useEffect(() => {
    setChat([]);
    setChatInput("");
    chatSessionRef.current = null;
    if (!open) return;
    let cancelled = false;
    const hydrate = async (): Promise<void> => {
      try {
        let sid = readStoredSession(surface, ref_);
        if (!sid) {
          const route = currentRoutePath();
          const list = await apiGet<{ items?: ChatSessionSummaryT[] }>(
            "/api/v1/chat/sessions", { limit: 10 },
          );
          sid = (list.items ?? []).find(
            (it) => (it.page_context?.route ?? "") === route,
          )?.id ?? null;
        }
        if (!sid || cancelled) return;
        const detail = await apiGet<ChatSessionDetailT>(
          `/api/v1/chat/sessions/${encodeURIComponent(sid)}`,
        );
        if (cancelled) return;
        chatSessionRef.current = detail.id;
        writeStoredSession(surface, ref_, detail.id);
        const turns: ChatTurn[] = (detail.messages ?? [])
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({
            role: m.role === "user" ? ("user" as const) : ("ai" as const),
            text: m.content_markdown,
            messageId: m.role === "assistant" ? m.id : undefined,
            citedEvidenceIds: m.cited_evidence_ids ?? [],
          }));
        if (turns.length) setChat(turns);
      } catch {
        // Hydration is best-effort: a 403/404 (deleted or foreign
        // session) clears the stale pointer; network errors are silent.
        writeStoredSession(surface, ref_, null);
      }
    };
    void hydrate();
    return () => {
      cancelled = true;
    };
  }, [open, surface, ref_]);

  if (!open) {
    if (!onOpen) return null;
    return (
      <button
        type="button"
        className="ip-tab"
        onClick={onOpen}
        title="Open Intelligence"
        aria-label="Open intelligence panel"
      >
        ✦ INTELLIGENCE
      </button>
    );
  }

  const head = surfaceHead(surface, title);
  const starters = starterQuestions(surface);

  function openEvidence(eid: string): void {
    if (onEvidenceClick) {
      onEvidenceClick(eid);
      return;
    }
    // Fallback: append ?drawer=evidence&e=<eid> to the URL so the
    // page-level EvidenceDrawer (if present) opens scoped to this
    // evidence row. Pages without a drawer ignore the params harmlessly.
    const url = new URL(window.location.href);
    const hash = url.hash || "#/";
    const [path, qs = ""] = hash.replace(/^#/, "").split("?");
    const params = new URLSearchParams(qs);
    params.set("drawer", "evidence");
    params.set("e", eid);
    window.location.hash = `${path}?${params.toString()}`;
  }

  async function ask(
    question?: string,
    style: "concise" | "deeper" = "concise",
  ): Promise<void> {
    const q = (question ?? chatInput).trim();
    if (!q || chatPending) return;
    setChat((c) => [...c, { role: "user", text: q }, { role: "ai", text: "", pending: true }]);
    setChatInput("");
    setChatPending(true);
    try {
      const res = await apiPost<RagAnswerBody>("/api/v1/rag/answer", {
        question: q,
        page_context: {
          route: window.location.hash.replace(/^#/, "") || "/",
          surface,
          ref: ref_ || null,
        },
        response_style: style,
        max_paragraphs: style === "deeper" ? 5 : 3,
        require_citations: true,
        session_id: chatSessionRef.current,
      });
      if (res.session_id) {
        chatSessionRef.current = res.session_id;
        writeStoredSession(surface, ref_, res.session_id);
      }
      const answer = res.answer_markdown ?? "No answer returned.";
      setChat((c) => {
        const next = [...c];
        next[next.length - 1] = {
          role: "ai",
          text: answer,
          messageId: res.message_id,
          citations: res.citations ?? [],
          citedEvidenceIds: res.cited_evidence_ids ?? [],
          staleDisclaimer: res.stale_disclaimer || undefined,
          fallbackUsed: res.fallback_used === true,
        };
        return next;
      });
    } catch {
      setChat((c) => {
        const next = [...c];
        next[next.length - 1] = {
          role: "ai",
          text: "Couldn't reach the answer service — try again.",
        };
        return next;
      });
    } finally {
      setChatPending(false);
    }
  }

  /** "Deeper · Pro" — re-asks with response_style:"deeper" (Gemini Pro
   *  server-side). Uses the last user question when there is one, else
   *  a surface-scoped deep-dive prompt. */
  function askDeeper(): void {
    const lastQ = [...chat].reverse().find((t) => t.role === "user")?.text;
    void ask(
      lastQ ??
        `Go deeper on ${head.title.toLowerCase()} for this entity — expand the analysis with specifics and cite evidence.`,
      "deeper",
    );
  }

  async function sendFeedback(
    turnIndex: number,
    messageId: string,
    rating: 1 | -1,
  ): Promise<void> {
    try {
      await apiPost(
        `/api/v1/chat/messages/${encodeURIComponent(messageId)}/feedback`,
        { rating },
      );
      setChat((c) => c.map((t, i) => (i === turnIndex ? { ...t, feedback: rating } : t)));
      pushToast("Feedback recorded", "success");
    } catch {
      pushToast("Couldn't record feedback", "warn");
    }
  }

  return (
    <aside className="ip" role="complementary" aria-label="Intelligence panel">
      <div className="ip-head">
        <div className="ai">✦</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="title txt-fit-1">{head.title}</div>
          <div className="sub txt-fit-1">{head.sub}</div>
        </div>
        <button
          type="button"
          className="icon-btn"
          onClick={onClose}
          aria-label="Close intelligence panel"
        >
          <Icon name="x" size={14} />
        </button>
      </div>

      <div ref={bodyRef} className="ip-body">
        {phase === "opening" ? (
          <div className="ip-opening" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Spinner /> Opening stream for {surface}…
          </div>
        ) : null}

        {phase === "fallback" ? (
          <div className="intel-fallback-banner" role="alert">
            <strong>{fallbackBannerCopy(fallbackFlags)}</strong>
            {fallbackFlags && Object.keys(fallbackFlags).length > 0 ? (
              <details className="intel-fallback-details">
                <summary>Flag detail</summary>
                <pre>{JSON.stringify(fallbackFlags, null, 2)}</pre>
              </details>
            ) : null}
          </div>
        ) : null}

        {text ? (
          <div style={{ fontSize: 13, lineHeight: 1.65, whiteSpace: "pre-wrap" }}>
            {text}
            {phase === "streaming" ? <span className="ip-cursor" /> : null}
          </div>
        ) : null}

        {(phase === "done" || phase === "fallback") && text ? (
          <div style={{ marginTop: 10, display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-tertiary btn-sm"
              onClick={() => {
                navigator.clipboard.writeText(text).then(
                  () => pushToast("Copied response", "success"),
                  () => pushToast("Couldn't access clipboard", "warn"),
                );
              }}
            >
              <Icon name="copy" size={12} /> Copy
            </button>
            <button
              type="button"
              className="btn btn-tertiary btn-sm"
              onClick={() => setStreamNonce((n) => n + 1)}
            >
              <Icon name="refresh" size={12} /> Regenerate
            </button>
            <button
              type="button"
              className="btn btn-tertiary btn-sm"
              onClick={askDeeper}
              disabled={chatPending}
              aria-label="Deeper analysis via Gemini Pro"
            >
              Deeper · Pro
            </button>
          </div>
        ) : null}

        {(phase === "done" || phase === "fallback") && citedEvidenceIds.length > 0 ? (
          <div className="intel-cited" style={{ marginTop: 12 }}>
            <strong>Cited evidence:</strong>{" "}
            {citedEvidenceIds.map((eid) => (
              <button
                key={eid}
                type="button"
                className="evidence-chip"
                onClick={() => openEvidence(eid)}
                aria-label={`Open evidence ${eid}`}
              >
                {eid}
              </button>
            ))}
          </div>
        ) : null}

        {surface === "why_now" && (phase === "done" || phase === "fallback") ? (
          <WhyNowSignals signals={whyNowSignals} onEvidence={openEvidence} />
        ) : null}

        {chat.length > 0 ? (
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--ph0-bd)" }}>
            {chat.map((m, i) => (
              <div key={i} className={`ip-message ${m.role}`}>
                {m.role === "ai" && m.staleDisclaimer ? (
                  <div
                    className="intel-stale-disclaimer"
                    style={{ fontSize: 11, color: "var(--z-org)", marginBottom: 4 }}
                  >
                    {m.staleDisclaimer}
                  </div>
                ) : null}
                {m.role === "ai" && m.fallbackUsed ? (
                  <span className="b b-org" style={{ marginRight: 6 }}>Fallback</span>
                ) : null}
                <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
                {m.pending ? <span className="ip-cursor" /> : null}
                {m.role === "ai" && !m.pending &&
                (m.citations?.length || m.citedEvidenceIds?.length) ? (
                  <div className="intel-cited" style={{ marginTop: 6 }}>
                    {(m.citations?.length
                      ? m.citations.map((c) => c.e_id)
                      : m.citedEvidenceIds ?? []
                    ).map((eid) => (
                      <button
                        key={eid}
                        type="button"
                        className="evidence-chip"
                        title={
                          m.citations?.find((c) => c.e_id === eid)?.source_name ?? eid
                        }
                        onClick={() => openEvidence(eid)}
                        aria-label={`Open evidence ${eid}`}
                      >
                        {eid}
                      </button>
                    ))}
                  </div>
                ) : null}
                {m.role === "ai" && !m.pending && m.messageId ? (
                  <div style={{ marginTop: 6, display: "flex", gap: 4 }}>
                    <button
                      type="button"
                      className="btn btn-tertiary btn-sm"
                      style={m.feedback === 1 ? { borderColor: "var(--z-teal)" } : undefined}
                      disabled={m.feedback != null}
                      onClick={() => void sendFeedback(i, m.messageId!, 1)}
                      aria-label="Mark answer helpful"
                    >
                      👍
                    </button>
                    <button
                      type="button"
                      className="btn btn-tertiary btn-sm"
                      style={m.feedback === -1 ? { borderColor: "var(--z-org)" } : undefined}
                      disabled={m.feedback != null}
                      onClick={() => void sendFeedback(i, m.messageId!, -1)}
                      aria-label="Mark answer unhelpful"
                    >
                      👎
                    </button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}

        {connNote ? (
          <div className="intel-reconnecting muted">{connNote}</div>
        ) : null}
      </div>

      {!chatPending ? (
        <div className="ip-chat">
          <div
            style={{
              fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em",
              color: "var(--z-dpur)", textTransform: "uppercase", marginBottom: 6,
            }}
          >
            {chat.length === 0 ? "Try a question" : "Follow-ups"}
          </div>
          {starters.map((s) => (
            <button key={s} type="button" className="ip-starter" onClick={() => void ask(s)}>
              {s}
            </button>
          ))}
        </div>
      ) : null}

      <div className="ip-input">
        <input
          placeholder="Ask anything about this entity…"
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void ask()}
          aria-label="Ask the intelligence panel"
        />
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => void ask()}
          disabled={!chatInput.trim() || chatPending}
          aria-label="Send question"
        >
          <Icon name="arrow-r" size={12} />
        </button>
      </div>
    </aside>
  );
}
