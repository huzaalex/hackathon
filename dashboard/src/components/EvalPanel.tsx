import { useEffect } from "react";
import { EvalState, fmtDuration, fmtPct, fmtUsd, OUTCOME_LABEL } from "../api";

interface Props {
  state: EvalState | null;
  onClose: () => void;
  onStart: () => void;
  onOpenCase: (id: string) => void;
}

const RESULT_LABEL: Record<string, string> = {
  PENDING: "Pending", RUNNING: "Running", PASS: "Pass", FAIL: "Fail", ERROR: "Error", TIMEOUT: "Timeout",
};

export default function EvalPanel({ state, onClose, onStart, onOpenCase }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const running = state?.status === "RUNNING";
  const s = state?.summary;
  const items = state?.items ?? [];
  const current = items.find((i) => i.status === "RUNNING");
  const progress = s && s.total ? s.completed / s.total : 0;

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="eval-title">
        <div className="modal-head">
          <div>
            <h2 id="eval-title">Evaluation</h2>
            <p className="muted">
              Replays every demo scenario end to end and checks the result against the expected outcome, client and amount
              held (golden set). It resets the demo data first, answers operator questions with scripted answers and makes
              real LLM calls, so a full run takes about 15-20 minutes.
            </p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden>
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        <div className="eval-actions">
          <button className="btn primary" onClick={onStart} disabled={running}>
            {running ? "Evaluation running…" : state?.status === "IDLE" || !state ? "Start evaluation" : "Run again"}
          </button>
          {state?.started_at && (
            <span className="muted small">
              Started {state.started_at.slice(11)}{state.finished_at && !running ? ` · finished ${state.finished_at.slice(11)}` : ""}
            </span>
          )}
        </div>

        {state && state.status !== "IDLE" && (
          <>
            <div className="eval-progress" aria-label="Progress">
              <div className="bar"><span style={{ width: `${progress * 100}%` }} /></div>
              <span className="small">
                {s?.completed ?? 0} of {s?.total ?? items.length} scenarios
                {current ? ` · now: ${current.title}` : ""}
              </span>
            </div>
            {state.error && <p className="err small">Evaluation stopped: {state.error}</p>}

            {s && s.completed > 0 && (
              <div className="eval-tiles">
                <Tile label="Scenarios passed" value={`${s.scenarios_passed}/${s.completed}`} tone="green" />
                <Tile label="Outcome accuracy" value={fmtPct(s.outcome_accuracy)} tone="yellow" />
                <Tile label="Checks passed" value={`${s.checks_passed}/${s.checks_total}`} tone="teal" />
                <Tile label="No operator needed" value={fmtPct(s.automation_rate)} tone="indigo" />
                <Tile label="Avg time per case" value={fmtDuration(s.avg_processing_seconds)} tone="plum" />
                <Tile label="Avg cost per case" value={fmtUsd(s.avg_cost_usd)} tone="coral" />
              </div>
            )}

            <div className="eval-table-wrap">
              <table className="grid eval-table">
                <thead>
                  <tr><th>#</th><th>Scenario</th><th>Result</th><th>Checks</th><th>Time</th><th>Cost</th><th>Operator</th><th /></tr>
                </thead>
                <tbody>
                  {items.map((it, i) => (
                    <tr key={it.file} className={`row-${it.status}`}>
                      <td className="mono">{String(i + 1).padStart(2, "0")}</td>
                      <td>
                        <strong>{it.title}</strong>
                        {it.outcome && <span className="muted small block">{OUTCOME_LABEL[it.outcome] ?? it.outcome}</span>}
                      </td>
                      <td><span className={`result-chip ${it.status}`}>{RESULT_LABEL[it.status]}</span></td>
                      <td>
                        <span className="check-list">
                          {it.checks.map((c) => (
                            <span key={c.name} className={`check ${c.passed ? "ok" : "bad"}`} title={`Expected: ${c.expected} · Actual: ${c.actual}`}>
                              {c.name}
                            </span>
                          ))}
                        </span>
                      </td>
                      <td>{it.processing_seconds != null ? fmtDuration(it.processing_seconds) : "-"}</td>
                      <td>{it.cost_usd != null ? fmtUsd(it.cost_usd) : "-"}</td>
                      <td>{it.operator_interventions ? `${it.operator_interventions} answer(s)` : it.status === "PENDING" ? "-" : "None"}</td>
                      <td>
                        {it.case_id && (
                          <button className="btn small ghost" onClick={() => onOpenCase(it.case_id!)}>Open</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small">Hover a check to see the expected and actual values. Cost is estimated at list price.</p>
          </>
        )}
      </div>
    </div>
  );
}

function Tile({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className={`impact-tile tone-${tone}`}>
      <span className="impact-label">{label}</span>
      <span className="impact-value">{value}</span>
    </div>
  );
}
