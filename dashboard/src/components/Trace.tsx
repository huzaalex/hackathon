import { ReactNode, useEffect, useRef, useState } from "react";
import { AgentEvent, OUTCOME_LABEL, STATUS_LABEL, CaseStatus } from "../api";

const AGENT_CLASS: Record<string, string> = {
  Supervisor: "a-sup",
  "Reader Agent": "a-cit",
  "Identification Agent": "a-id",
  "Legal Agent": "a-jur",
  "Action Agent": "a-act",
  Operator: "a-op",
  System: "a-sys",
};

export default function Trace({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  const [technical, setTechnical] = useState(false);

  useEffect(() => {
    if (follow) end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length, follow]);

  return (
    <div className="trace">
      <div className="trace-controls">
        <label>
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow live
        </label>
        <label>
          <input type="checkbox" checked={technical} onChange={(e) => setTechnical(e.target.checked)} /> Show technical details
        </label>
      </div>
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
      {running && <div className="typing">The agents are working…</div>}
      <div ref={end} />
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
          <Collapsible text={text} limit={320} />
        </div>
      );
      break;
    case "text":
      body = <p className="say">{text}</p>;
      break;
    case "tool_call":
      body = <p className={d.tool?.endsWith("_agent") ? "delegate" : "action"}>{text}</p>;
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
        <p className="agent-result">
          <strong>Result: </strong>
          {text}
        </p>
      );
      raw = d.result;
      break;
    case "review_requested":
      body = (
        <p className="review-req">
          <strong>Asked a human operator: </strong>
          {d.question ?? text}
        </p>
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
          <strong>Case closed: {OUTCOME_LABEL[d.outcome] ?? d.outcome}</strong>
          <p>{d.summary}</p>
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

function Collapsible({ text, limit }: { text: string; limit: number }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  if (text.length <= limit) return <span>{text}</span>;
  return (
    <span>
      {open ? text : text.slice(0, limit) + "… "}
      <button className="linkbtn" onClick={() => setOpen(!open)}>{open ? "Show less" : "Show more"}</button>
    </span>
  );
}
