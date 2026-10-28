import { ReactNode, useEffect, useRef, useState } from "react";
import { AgentEvent } from "../api";

const AGENT_CLASS: Record<string, string> = {
  Supervizor: "a-sup",
  "Agent Citire": "a-cit",
  "Agent Identificare": "a-id",
  "Agent Juridic": "a-jur",
  "Agent Acțiune": "a-act",
  Operator: "a-op",
  Sistem: "a-sys",
};

export default function Trace({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);

  useEffect(() => {
    if (follow) end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length, follow]);

  return (
    <div className="trace">
      <label className="follow">
        <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> urmărește live
      </label>
      {events.map((ev) => (
        <EventRow key={ev.seq} ev={ev} />
      ))}
      {running && <div className="typing">agenții lucrează…</div>}
      <div ref={end} />
    </div>
  );
}

function EventRow({ ev }: { ev: AgentEvent }) {
  const d = ev.data;
  let body: ReactNode;
  switch (ev.type) {
    case "thinking":
      body = <Collapsible className="thinking" text={d.text} limit={280} />;
      break;
    case "text":
      body = <p className="say">{d.text}</p>;
      break;
    case "agent_start":
      body = <p className="delegate">▶ pornește{d.instructions ? `: ${d.instructions}` : ""}</p>;
      break;
    case "tool_call":
      body = (
        <p className="tool">
          🔧 <code>{d.tool}</code>
          {d.input && Object.keys(d.input).length > 0 && <code className="args">{JSON.stringify(d.input)}</code>}
        </p>
      );
      break;
    case "tool_result":
      body = (
        <div className={`result ${d.ok ? "ok" : "fail"}`}>
          <span>{d.ok ? "✓" : "✗"} {d.tool}</span>
          <Collapsible className="mono" text={d.preview} limit={160} />
        </div>
      );
      break;
    case "agent_result":
      body = (
        <details className="agent-result">
          <summary>✔ rezultat trimis supervizorului</summary>
          <pre>{JSON.stringify(d.result, null, 2)}</pre>
        </details>
      );
      break;
    case "review_requested":
      body = <p className="review-req">🙋 Cere confirmarea operatorului: {d.question}</p>;
      break;
    case "review_answered":
      body = <p className="review-ans">Operatorul a răspuns: „{d.answer}”</p>;
      break;
    case "case_finished":
      body = <p className="finished">🏁 {d.outcome}: {d.summary}</p>;
      break;
    case "error":
      body = <p className="err">⚠ {d.message}</p>;
      break;
    case "status":
      body = <p className="muted small">status → {d.status}</p>;
      break;
    case "case_created":
      body = <p className="muted small">caz creat ({d.kind}): {d.title}</p>;
      break;
    default:
      body = <pre>{JSON.stringify(d)}</pre>;
  }
  return (
    <div className={`event ev-${ev.type}`}>
      <span className="ts">{ev.ts.slice(11)}</span>
      <span className={`agent ${AGENT_CLASS[ev.agent] ?? "a-sys"}`}>{ev.agent}</span>
      <div className="body">{body}</div>
    </div>
  );
}

function Collapsible({ text, limit, className }: { text: string; limit: number; className?: string }) {
  const [open, setOpen] = useState(false);
  if (!text) return null;
  if (text.length <= limit) return <p className={className}>{text}</p>;
  return (
    <p className={className}>
      {open ? text : text.slice(0, limit) + "… "}
      <button className="linkbtn" onClick={() => setOpen(!open)}>{open ? "mai puțin" : "mai mult"}</button>
    </p>
  );
}
