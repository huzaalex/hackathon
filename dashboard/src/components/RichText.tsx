import { useState } from "react";

// "Debtor: Ion Popescu ..." -> the label is shown in bold
const LABEL = /^([A-Z][A-Za-z /&-]{1,24}):\s+/;

function Line({ text }: { text: string }) {
  const m = text.match(LABEL);
  if (!m) return <>{text}</>;
  return (
    <>
      <strong className="rt-label">{m[1]}:</strong> {text.slice(m[0].length)}
    </>
  );
}

/** Renders agent text as paragraphs (blank line) and line breaks (single newline). */
export function RichText({ text, className = "" }: { text: string; className?: string }) {
  const paragraphs = (text || "").trim().split(/\n\s*\n/).filter(Boolean);
  return (
    <div className={`rich ${className}`}>
      {paragraphs.map((p, i) => (
        <p key={i}>
          {p.split("\n").map((line, j) => (
            <span key={j}>
              {j > 0 && <br />}
              <Line text={line.trim()} />
            </span>
          ))}
        </p>
      ))}
    </div>
  );
}

/** Shows the beginning of a long text with a "See more" button that reveals the rest. */
export function ExpandableText({ text, limit = 240, className = "" }: { text: string; limit?: number; className?: string }) {
  const [open, setOpen] = useState(false);
  const full = (text || "").trim();
  if (!full) return null;
  const long = full.length > limit;
  const preview = long ? full.slice(0, limit).replace(/\s+\S*$/, "") + "…" : full;
  return (
    <div className={`expandable ${className}`}>
      <RichText text={open || !long ? full : preview} />
      {long && (
        <button type="button" className="see-more" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "See less" : "See more"}
          <svg className="chev" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
      )}
    </div>
  );
}
