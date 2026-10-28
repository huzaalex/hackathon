import { useState } from "react";
import { api, Review } from "../api";

export default function ReviewPanel({ caseId, review, onAnswered }: { caseId: string; review: Review; onAnswered: () => void }) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  const send = async (answer: string) => {
    if (!answer.trim()) return;
    setSending(true);
    try {
      await api.review(caseId, answer);
      onAnswered();
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="review">
      <h4>🙋 Agentul cere decizia unui operator</h4>
      <p className="question">{review.question}</p>
      {review.context && <p className="muted">{review.context}</p>}
      <div className="options">
        {review.options.map((o) => (
          <button key={o} className="btn" disabled={sending} onClick={() => send(o)}>{o}</button>
        ))}
      </div>
      <div className="row">
        <input placeholder="Sau scrie un răspuns liber…" value={text} onChange={(e) => setText(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && send(text)} />
        <button className="btn ghost" disabled={sending || !text.trim()} onClick={() => send(text)}>Trimite</button>
      </div>
    </div>
  );
}
