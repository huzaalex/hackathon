import { useEffect, useState } from "react";
import { api, fmtDuration, fmtPct, fmtUsd, Metrics } from "../api";

/** Live impact of the agents over the cases processed in this session. */
export default function ImpactBar() {
  const [m, setM] = useState<Metrics | null>(null);

  useEffect(() => {
    const load = () => api.metrics().then(setM).catch(() => undefined);
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  if (!m) return null;
  const saved = m.manual_minutes_saved;
  const tiles = [
    { tone: "yellow", label: "Cases processed", value: String(m.cases_done), hint: m.in_progress ? `${m.in_progress} in progress` : "this session" },
    { tone: "indigo", label: "No operator needed", value: fmtPct(m.automation_rate), hint: `${m.automated} of ${m.cases_done} cases` },
    { tone: "teal", label: "Avg AI processing time", value: fmtDuration(m.avg_processing_seconds), hint: "per case, end to end" },
    { tone: "plum", label: "Est. AI cost per case", value: fmtUsd(m.avg_cost_usd), hint: `${fmtUsd(m.total_cost_usd)} in total` },
    { tone: "green", label: "Manual work saved", value: fmtDuration(saved * 60), hint: `vs ${m.assumptions.manual_minutes_per_case} min per order by hand` },
    { tone: "coral", label: "Forged orders stopped", value: String(m.frauds_stopped), hint: "before any money moved" },
  ];

  return (
    <section className="impact" aria-label="Impact">
      <div className="impact-tiles">
        {tiles.map((t) => (
          <div key={t.label} className={`impact-tile tone-${t.tone}`}>
            <span className="impact-label">{t.label}</span>
            <span className="impact-value">{t.value}</span>
            <span className="impact-hint">{t.hint}</span>
          </div>
        ))}
      </div>
      <p className="impact-note">
        Estimates: {m.assumptions.manual_minutes_per_case} min of manual work per order and {m.assumptions.operator_minutes_per_review} min per
        operator decision (baseline to be confirmed in the bank interview); AI cost at list price for {m.assumptions.model} (
        ${m.assumptions.price_input_per_mtok} / ${m.assumptions.price_output_per_mtok} per million input / output tokens), Bedrock pricing may differ.
      </p>
    </section>
  );
}
