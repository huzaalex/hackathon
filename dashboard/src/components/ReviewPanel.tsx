import { useState } from "react";
import { api, Review } from "../api";

export default function ReviewPanel({ caseId, review, onAnswered }: { caseId: string; review: Review; onAnswered: () => void }) {
  const [choice, setChoice] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const answer = (text.trim() || choice || "").trim();

  const send = async () => {
    if (!answer) return;
    setSending(true);
    setError(null);
    try {
      await api.review(caseId, answer);
      onAnswered();
    } catch (e) {
      setError(String(e));
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="review" aria-labelledby="review-title">
      <div className="review-head">
        <span className="badge NEEDS_REVIEW">Operator decision needed</span>
        <h4 id="review-title">{review.question}</h4>
        {review.context && <p className="muted">{review.context}</p>}
      </div>

      {review.options.length > 0 && (
        <div className="options" role="radiogroup" aria-label="Suggested answers">
          {review.options.map((o, i) => (
            <button
              key={o}
              role="radio"
              aria-checked={choice === o}
              className={`option ${choice === o ? "selected" : ""}`}
              disabled={sending}
              onClick={() => {
                setChoice(o);
                setText("");
              }}
            >
              <span className="option-key">{String.fromCharCode(65 + i)}</span>
              <span className="option-text">{o}</span>
            </button>
          ))}
        </div>
      )}

      <label className="free-answer">
        <span>Or write your own answer</span>
        <textarea
          rows={2}
          placeholder="For example: it is client CL005, the address matches the bailiff's file."
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (e.target.value) setChoice(null);
          }}
        />
      </label>

      <div className="review-actions">
        <button className="btn" disabled={sending || !answer} onClick={send}>
          {sending ? "Sending…" : "Send answer and resume"}
        </button>
        {error && <span className="err small">{error}</span>}
      </div>
    </section>
  );
}
