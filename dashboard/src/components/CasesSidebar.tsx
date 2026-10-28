import { CaseSummary, OUTCOME_LABEL, STATUS_LABEL } from "../api";

interface Props {
  open: boolean;
  onToggle: () => void;
  cases: CaseSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}

export default function CasesSidebar({ open, onToggle, cases, selected, onSelect }: Props) {
  const waiting = cases.filter((c) => c.status === "NEEDS_REVIEW").length;
  return (
    <>
      <aside className={`cases-sidebar ${open ? "open" : ""}`} aria-label="Case history" aria-hidden={!open}>
        <div className="cases-head">
          <h2>Cases</h2>
          <span className="count">{cases.length}</span>
        </div>
        {waiting > 0 && <p className="waiting">{waiting} case(s) waiting for an operator</p>}
        {!cases.length && <p className="muted small">No cases yet. Upload a file or run a demo.</p>}
        <ul>
          {cases.map((c) => (
            <li key={c.id}>
              <button className={`case-item ${c.id === selected ? "active" : ""}`} onClick={() => onSelect(c.id)} tabIndex={open ? 0 : -1}>
                <span className="case-head">
                  <span className="case-id">{c.id}</span>
                  <span className={`badge ${c.status}`}>{STATUS_LABEL[c.status]}</span>
                </span>
                <span className="case-title">
                  <span className={`kind ${c.kind}`}>{c.kind === "EVENT" ? "Event" : "Document"}</span>
                  {c.title}
                </span>
                {c.outcome && <span className="case-outcome">{OUTCOME_LABEL[c.outcome] ?? c.outcome}</span>}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <button
        className={`sidebar-toggle ${open ? "open" : ""}`}
        onClick={onToggle}
        aria-expanded={open}
        aria-label={open ? "Hide case history" : "Show case history"}
        title={open ? "Hide cases" : "Show cases"}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
          {open ? <path d="M15 6l-6 6 6 6" /> : <path d="M9 6l6 6-6 6" />}
        </svg>
        {!open && (
          <span className="toggle-label">
            Cases{cases.length ? ` (${cases.length})` : ""}
            {waiting > 0 && <span className="toggle-alert" aria-label={`${waiting} waiting`} />}
          </span>
        )}
      </button>
    </>
  );
}
