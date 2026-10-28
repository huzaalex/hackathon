import type { ReactNode } from "react";
import { fmtMoney } from "../api";

const DOC_FIELDS: [string, string][] = [
  ["tip_document", "Tip document"],
  ["emitent_tip", "Tip emitent"],
  ["emitent_nume", "Emitent"],
  ["numar_dosar", "Nr. dosar"],
  ["numar_inregistrare", "Nr. adresă"],
  ["debitor_nume", "Debitor"],
  ["debitor_cnp", "CNP (din document)"],
  ["cnp_valid", "CNP valid"],
  ["debitor_adresa", "Adresă"],
  ["creditor", "Creditor"],
  ["suma", "Sumă"],
  ["moneda", "Monedă"],
  ["tip_creanta", "Tip creanță"],
  ["descriere_creanta", "Descriere"],
  ["iban_virare", "IBAN virare"],
  ["incredere", "Încredere extragere"],
];

const show = (v: unknown) => (v === null || v === undefined || v === "" ? "–" : typeof v === "boolean" ? (v ? "da" : "NU") : String(v));

export default function Blackboard({ data }: { data: Record<string, any> }) {
  const { document: doc, identificare: id, juridic, plan_blocare: plan, scrisoare, actiuni, eveniment } = data;
  const known = new Set(["document", "identificare", "juridic", "plan_blocare", "scrisoare", "actiuni", "eveniment", "extragere_text"]);
  const others = Object.entries(data).filter(([k]) => !known.has(k));

  return (
    <div className="blackboard">
      {eveniment && (
        <Card title="Eveniment core banking">
          <p>
            Încasare {fmtMoney(eveniment.amount, eveniment.currency)} în contul <code>{eveniment.iban}</code> (sursa{" "}
            {eveniment.source}) pentru clientul {eveniment.client_id}.
          </p>
        </Card>
      )}

      {doc && (
        <Card title="1 · Document extras (Agent Citire)">
          {data.extragere_text && (
            <p className="muted small">
              {data.extragere_text.strat_text ? "PDF cu strat de text" : "PDF scanat – citit vizual"} ·{" "}
              {data.extragere_text.pagini} pagini
            </p>
          )}
          <table className="kv">
            <tbody>
              {DOC_FIELDS.map(([k, label]) => (
                <tr key={k}>
                  <th>{label}</th>
                  <td className={k === "cnp_valid" && doc[k] === false ? "warn" : ""}>{show(doc[k])}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {doc.probleme?.length > 0 && (
            <ul className="issues">{doc.probleme.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul>
          )}
        </Card>
      )}

      {id && (
        <Card title="2 · Identificare debitor (Agent Identificare)">
          <p>
            <span className={`badge id-${id.status}`}>{id.status}</span> {id.client_id && <strong>{id.client_id}</strong>}{" "}
            <span className="muted">încredere {show(id.incredere)}</span>
          </p>
          {id.cnp_corectat && <p>CNP corectat: <code>{id.cnp_corectat}</code></p>}
          <p>{id.motivare}</p>
          {id.candidati?.length > 0 && (
            <ul>{id.candidati.map((c: any) => <li key={c.client_id}><strong>{c.client_id}</strong> – {c.motiv}</li>)}</ul>
          )}
        </Card>
      )}

      {juridic && (
        <Card title="3 · Decizie juridică (Agent Juridic)">
          <p>
            <span className="badge">{juridic.decizie}</span> {juridic.tip_creanta && <span className="pill">{juridic.tip_creanta}</span>}
          </p>
          <p>{juridic.rezumat}</p>
          {juridic.temei_legal?.length > 0 && (
            <ul className="legal">{juridic.temei_legal.map((t: string, i: number) => <li key={i}>{t}</li>)}</ul>
          )}
        </Card>
      )}

      {plan && (
        <Card title="Plan de blocare (motor de reguli determinist)">
          <ol className="explain">{plan.explanation.map((l: string, i: number) => <li key={i}>{l}</li>)}</ol>
          <table className="grid">
            <thead>
              <tr><th>Poprire</th><th>Tip</th><th>Rang</th><th>Solicitat</th><th>Alocat</th><th>Rămas</th></tr>
            </thead>
            <tbody>
              {plan.garnishments.map((g: any) => (
                <tr key={g.id}>
                  <td>{g.id}</td><td>{g.claim_label}</td><td>{g.rank}</td>
                  <td>{fmtMoney(g.requested_ron)}</td><td><strong>{fmtMoney(g.allocated_ron)}</strong></td>
                  <td className={g.remaining_ron > 0 ? "warn" : ""}>{fmtMoney(g.remaining_ron)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {plan.holds.length > 0 && (
            <table className="grid">
              <thead><tr><th>Cont</th><th>Poprire</th><th>Sumă blocată</th><th>Echivalent RON</th></tr></thead>
              <tbody>
                {plan.holds.map((h: any, i: number) => (
                  <tr key={i}>
                    <td><code>{h.iban}</code></td><td>{h.garnishment_id}</td>
                    <td>{fmtMoney(h.amount, h.currency)}</td><td>{fmtMoney(h.amount_ron)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted small">
            Curs BNR: {show(plan.curs_bnr?.data)} ({show(plan.curs_bnr?.sursa)}). {plan.disclaimer}
          </p>
        </Card>
      )}

      {(actiuni || scrisoare) && (
        <Card title="4 · Acțiuni executate (Agent Acțiune)">
          {actiuni?.actiuni_efectuate && <ul>{actiuni.actiuni_efectuate.map((a: string, i: number) => <li key={i}>{a}</li>)}</ul>}
          {actiuni?.probleme?.length > 0 && <ul className="issues">{actiuni.probleme.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul>}
          {scrisoare && (
            <div className="letter">
              <p><strong>Scrisoare {scrisoare.referinta}</strong> ({scrisoare.tip}) către {scrisoare.destinatar}</p>
              {scrisoare.paragrafe.map((p: string, i: number) => <p key={i}>{p}</p>)}
            </div>
          )}
        </Card>
      )}

      {others.map(([k, v]) => (
        <Card key={k} title={k}>
          <pre>{JSON.stringify(v, null, 2)}</pre>
        </Card>
      ))}

      {!Object.keys(data).length && <p className="muted">Încă nu există date. Agenții completează blackboard-ul pe parcurs.</p>}
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card">
      <h4>{title}</h4>
      {children}
    </section>
  );
}
