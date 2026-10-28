import { ReactNode, useEffect, useRef, useState } from "react";
import { AgentEvent, OUTCOME_LABEL, STATUS_LABEL, CaseStatus } from "../api";
import { ExpandableText } from "./RichText";

const AGENT_CLASS: Record<string, string> = {
  Supervisor: "a-sup",
  "Reader Agent": "a-cit",
  "Authenticity Agent": "a-auth",
  "Identification Agent": "a-id",
  "Legal Agent": "a-jur",
  "Action Agent": "a-act",
  Operator: "a-op",
  System: "a-sys",
};

const NEAR_BOTTOM_PX = 48;

export default function Trace({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const [technical, setTechnical] = useState(false);
  const [unseen, setUnseen] = useState(0);

  // Follow mode scrolls only inside the trace panel, never the page, so the user can always scroll freely.
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    if (follow) {
      el.scrollTop = el.scrollHeight;
      setUnseen(0);
    } else {
      setUnseen((n) => n + 1);
    }
  }, [events.length]);

  // Scrolling up inside the panel pauses following; scrolling back to the bottom resumes it.
  const onScroll = () => {
    const el = box.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
    if (atBottom !== follow) setFollow(atBottom);
    if (atBottom) setUnseen(0);
  };

  const jumpToLatest = () => {
    const el = box.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    setFollow(true);
    setUnseen(0);
  };

  return (
    <div className="trace">
      <div className="trace-controls">
        <label>
          <input type="checkbox" checked={follow} onChange={(e) => (e.target.checked ? jumpToLatest() : setFollow(false))} /> Follow live
        </label>
        <label>
          <input type="checkbox" checked={technical} onChange={(e) => setTechnical(e.target.checked)} /> Show technical details
        </label>
      </div>
      <div className="trace-scroll" ref={box} onScroll={onScroll}>
        {events.map((ev) =>
          ev.type === "agent_start" ? (
            <div key={ev.seq} className="divider">
              <span className={`agent ${AGENT_CLASS[ev.agent] ?? "a-sys"}`}>{ev.agent}</span>
              <span>started working</span>
            </div>
          ) : (
            <EventRow key={ev.seq} ev={ev} technical={technical} />
          ),
        )}
        {running && (
          <div className="typing" role="status">
            <span className="dots" aria-hidden><i /><i /><i /></span>
            The agents are working
          </div>
        )}
        {!follow && unseen > 0 && (
          <button type="button" className="jump-latest" onClick={jumpToLatest}>
            {unseen} new update{unseen > 1 ? "s" : ""} · Jump to latest
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

function EventRow({ ev, technical }: { ev: AgentEvent; technical: boolean }) {
  const d = ev.data;
  const text: string = d.text ?? d.message ?? "";
  let body: ReactNode;
  let raw: unknown = null;

  switch (ev.type) {
    case "thinking":
      body = (
        <div className="thinking">
          <span className="tag">Thinking</span>
          <ExpandableText text={text} limit={200} />
        </div>
      );
      break;
    case "text":
      body = <p className="say">{text}</p>;
      break;
    case "tool_call":
      body = d.tool?.endsWith("_agent") ? <ExpandableText className="delegate" text={text} limit={220} /> : <p className="action">{text}</p>;
      raw = { tool: d.tool, input: d.input };
      break;
    case "tool_result":
      body = (
        <p className={`result ${d.ok ? "ok" : "fail"}`}>
          <span className="dot" aria-hidden />
          {text}
        </p>
      );
      raw = d.preview;
      break;
    case "agent_result":
      body = (
        <div className="agent-result">
          <span className="rt-head">Result</span>
          <ExpandableText text={text} limit={200} />
        </div>
      );
      raw = d.result;
      break;
    case "review_requested":
      body = (
        <div className="review-req">
          <span className="rt-head">Asked a human operator</span>
          <ExpandableText text={d.question ?? text} limit={240} />
        </div>
      );
      break;
    case "review_answered":
      body = (
        <p className="review-ans">
          <strong>Operator answered: </strong>
          {d.answer ?? text}
        </p>
      );
      break;
    case "case_finished":
      body = (
        <div className="finished">
          <span className="rt-head">Case closed: {OUTCOME_LABEL[d.outcome] ?? d.outcome}</span>
          <ExpandableText text={d.summary ?? ""} limit={240} />
        </div>
      );
      break;
    case "error":
      body = (
        <p className="err">
          <strong>Error: </strong>
          {text}
        </p>
      );
      break;
    case "status":
      body = <p className="muted small">Status changed to {STATUS_LABEL[d.status as CaseStatus] ?? d.status}</p>;
      break;
    case "case_created":
      body = <p className="muted small">Case created ({d.kind === "EVENT" ? "event" : "document"}): {d.title}</p>;
      break;
    default:
      body = <p>{text}</p>;
      raw = d;
  }

  return (
    <div className={`event ev-${ev.type}`}>
      <span className="ts">{ev.ts.slice(11)}</span>
      <span className={`agent ${AGENT_CLASS[ev.agent] ?? "a-sys"}`}>{ev.agent}</span>
      <div className="body">
        {body}
        {technical && raw != null && (
          <pre className="raw">{typeof raw === "string" ? raw : JSON.stringify(raw, null, 2)}</pre>
        )}
      </div>
    </div>
  );
}
