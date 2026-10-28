import { CaseStatus } from "../api";

// Each step has its own tone: yellow = you (upload), indigo = the AI at work, coral = the human operator
const STEPS = [
  {
    tone: "yellow",
    title: "Upload the order",
    text: "Drop a garnishment order from a bailiff, ANAF or a local tax office. Text PDFs and scans both work.",
  },
  {
    tone: "indigo",
    title: "Let the AI inspect",
    text: "Specialised agents read it, identify the debtor, apply the legal limits and act in core banking. Follow them live.",
  },
  {
    tone: "coral",
    title: "Intervene if necessary",
    text: "When the agents are not sure, the case pauses and asks you to decide. Everything else is automatic.",
  },
];

/** Where the selected case currently is in the 3-step flow. */
function stepState(status: CaseStatus | null): { active: number; done: number } {
  switch (status) {
    case "QUEUED":
    case "RUNNING":
    case "FAILED":
      return { active: 1, done: 1 };
    case "NEEDS_REVIEW":
      return { active: 2, done: 2 };
    case "DONE":
      return { active: -1, done: 3 };
    default:
      return { active: -1, done: 0 };
  }
}

export default function Steps({ status }: { status: CaseStatus | null }) {
  const { active, done } = stepState(status);
  return (
    <ol className="steps">
      {STEPS.map((s, i) => (
        <li key={s.title} className={`step tone-${s.tone} ${i === active ? "active" : ""} ${i < done ? "done" : ""}`}>
          <span className="step-num" aria-hidden>
            {i < done ? (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 12l5 5 9-10" />
              </svg>
            ) : (
              i + 1
            )}
          </span>
          <span className="step-label">
            Step {i + 1}
            {i === active && <span className="step-now">in progress</span>}
          </span>
          <h3>{s.title}</h3>
          <p>{s.text}</p>
        </li>
      ))}
    </ol>
  );
}
