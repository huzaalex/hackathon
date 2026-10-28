import { CaseSummary, OUTCOME_LABEL, STATUS_LABEL } from "../api";

interface Props {
  cases: CaseSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}

export default function CaseList({ cases, selected, onSelect }: Props) {
  return (
    <section className="cases">
      <h3>Cases ({cases.length})</h3>
      {!cases.length && <p className="muted">No cases yet.</p>}
      <ul>
        {cases.map((c) => (
          <li key={c.id} className={c.id === selected ? "active" : ""} onClick={() => onSelect(c.id)}>
            <div className="case-head">
              <span className="case-id">{c.id}</span>
              <span className={`badge ${c.status}`}>{STATUS_LABEL[c.status]}</span>
            </div>
            <div className="case-title">
              <span className={`kind ${c.kind}`}>{c.kind === "EVENT" ? "Event" : "Document"}</span>
              {c.title}
            </div>
            {c.outcome && <div className="case-outcome">{OUTCOME_LABEL[c.outcome] ?? c.outcome}</div>}
          </li>
        ))}
      </ul>
    </section>
  );
}
