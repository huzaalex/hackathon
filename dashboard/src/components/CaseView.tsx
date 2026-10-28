import { useEffect, useState } from "react";
import { AgentEvent, api, CaseDetail, OUTCOME_LABEL, STATUS_LABEL } from "../api";
import Trace from "./Trace";
import Blackboard from "./Blackboard";
import ClientPanel from "./ClientPanel";
import ReviewPanel from "./ReviewPanel";
import { ExpandableText } from "./RichText";

type Tab = "trace" | "data" | "client";

export default function CaseView({ caseId }: { caseId: string }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [tab, setTab] = useState<Tab>("trace");

  // Live trace over Server-Sent Events; the detail is refreshed whenever something meaningful happens
  useEffect(() => {
    setEvents([]);
    const load = () => api.caseDetail(caseId).then(setDetail).catch(() => undefined);
    load();
    const es = new EventSource(`/api/cases/${caseId}/stream`);
    es.onmessage = (msg) => {
      const ev: AgentEvent = JSON.parse(msg.data);
      setEvents((prev) => (prev.some((p) => p.seq === ev.seq) ? prev : [...prev, ev]));
      if (["status", "agent_result", "tool_result", "case_finished", "review_requested"].includes(ev.type)) load();
    };
    return () => es.close();
  }, [caseId]);

  if (!detail) return <p className="muted">Loading…</p>;

  return (
    <div className="case-view">
      <div className="case-header">
        <div>
          <h2>
            {detail.id} · {detail.title}
          </h2>
          <div className="meta">
            <span className={`badge ${detail.status}`}>{STATUS_LABEL[detail.status]}</span>
            {detail.outcome && <span className="pill outcome">{OUTCOME_LABEL[detail.outcome] ?? detail.outcome}</span>}
            <span className="muted small">
              {detail.usage.llm_calls} LLM calls · {detail.usage.input_tokens.toLocaleString("en-GB")} input /{" "}
              {detail.usage.output_tokens.toLocaleString("en-GB")} output tokens
            </span>
          </div>
        </div>
        <div className="actions">
          {detail.has_document && (
            <a className="btn ghost" href={`/api/cases/${detail.id}/document`} target="_blank" rel="noreferrer">
              Original document
            </a>
          )}
          {detail.has_response_pdf && (
            <a className="btn" href={`/api/cases/${detail.id}/response.pdf`} target="_blank" rel="noreferrer">
              Reply letter (PDF)
            </a>
          )}
        </div>
      </div>

      {detail.summary && (
        <div className="summary">
          <span className="rt-head">Case summary</span>
          <ExpandableText text={detail.summary} limit={420} />
        </div>
      )}
      {detail.status === "NEEDS_REVIEW" && detail.review && (
        <ReviewPanel caseId={detail.id} review={detail.review} onAnswered={() => api.caseDetail(caseId).then(setDetail)} />
      )}

      <nav className="tabs">
        <button className={tab === "trace" ? "on" : ""} onClick={() => setTab("trace")}>Agent reasoning</button>
        <button className={tab === "data" ? "on" : ""} onClick={() => setTab("data")}>Data &amp; decisions</button>
        <button className={tab === "client" ? "on" : ""} onClick={() => setTab("client")} disabled={!detail.client_id}>
          Client &amp; accounts
        </button>
      </nav>

      {tab === "trace" && <Trace events={events} running={detail.status === "RUNNING"} />}
      {tab === "data" && <Blackboard data={detail.blackboard} />}
      {tab === "client" && detail.client_id && <ClientPanel clientId={detail.client_id} version={events.length} />}
    </div>
  );
}
