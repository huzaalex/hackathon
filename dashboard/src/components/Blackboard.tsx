import type { ReactNode } from "react";
import { CLAIM_LABEL, fmtMoney, humanize } from "../api";

const DOC_TYPE: Record<string, string> = {
  GARNISHMENT_ORDER: "Garnishment order",
  GARNISHMENT_RELEASE: "Garnishment release",
  OTHER_DOCUMENT: "Other document",
};
const ISSUER_TYPE: Record<string, string> = {
  BAILIFF: "Bailiff",
  TAX_AUTHORITY: "Tax authority (ANAF)",
  LOCAL_TAX_AUTHORITY: "Local tax authority",
  OTHER: "Other",
};
const DECISION: Record<string, string> = {
  APPLY_GARNISHMENT: "Apply the garnishment",
  DUPLICATE: "Duplicate - no action",
  RELEASE: "Release the garnishment",
  REEVALUATE: "Re-evaluate the holds",
  NO_ACCOUNTS: "No accounts to garnish",
  NEEDS_OPERATOR: "Needs a human operator",
};
const LETTER: Record<string, string> = {
  GARNISHMENT_CONFIRMATION: "Garnishment confirmation",
  NO_ACCOUNTS: "Debtor has no accounts",
  RELEASE_CONFIRMATION: "Release confirmation",
  DUPLICATE_NOTICE: "Duplicate notice",
};

const show = (v: unknown) => (v === null || v === undefined || v === "" ? "-" : typeof v === "boolean" ? (v ? "Yes" : "No") : String(v));
const percent = (v: unknown) => (typeof v === "number" ? `${Math.round(v * 100)}%` : "-");

export default function Blackboard({ data }: { data: Record<string, any> }) {
  const { document: doc, identification: id, legal, allocation_plan: plan, letter, actions, event } = data;
  const { registered_garnishment: registered, applied_holds: applied, release } = data;
  const known = new Set(["document", "identification", "legal", "allocation_plan", "letter", "actions", "event", "text_extraction",
    "registered_garnishment", "applied_holds", "release"]);
  const others = Object.entries(data).filter(([k]) => !known.has(k));

  const docRows: [string, ReactNode][] = doc
    ? [
        ["Document type", humanize(doc.document_type, DOC_TYPE)],
        ["Issuer type", humanize(doc.issuer_type, ISSUER_TYPE)],
        ["Issuer", show(doc.issuer_name)],
        ["Case number", show(doc.case_number)],
        ["Letter number", show(doc.registration_number)],
        ["Debtor", show(doc.debtor_name)],
        ["CNP (as written)", show(doc.debtor_cnp)],
        ["CNP valid", <span className={doc.cnp_valid === false ? "warn" : ""}>{show(doc.cnp_valid)}</span>],
        ["Address", show(doc.debtor_address)],
        ["Creditor", show(doc.creditor)],
        ["Amount", doc.amount != null ? fmtMoney(doc.amount, doc.currency || "RON") : "-"],
        ["Claim type", humanize(doc.claim_type, CLAIM_LABEL)],
        ["Claim description", show(doc.claim_description)],
        ["Payment IBAN", show(doc.payment_iban)],
        ["Extraction confidence", percent(doc.confidence)],
      ]
    : [];

  return (
    <div className="blackboard">
      {event && (
        <Card title="Core banking event">
          <p>
            Incoming payment of {fmtMoney(event.amount, event.currency)} on account <code>{event.iban}</code> (source:{" "}
            {humanize(event.source)}) for client {event.client_id}.
          </p>
        </Card>
      )}

      {doc && (
        <Card title="1 · Extracted document (Reader Agent)">
          {data.text_extraction && (
            <p className="muted small">
              {data.text_extraction.text_layer ? "PDF with a text layer" : "Scanned PDF - read visually"} ·{" "}
              {data.text_extraction.pages} page(s) · original in Romanian
            </p>
          )}
          <table className="kv">
            <tbody>
              {docRows.map(([label, value]) => (
                <tr key={label}>
                  <th>{label}</th>
                  <td>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {doc.issues?.length > 0 && (
            <ul className="issues">{doc.issues.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul>
          )}
        </Card>
      )}

      {id && (
        <Card title="2 · Debtor identification (Identification Agent)">
          <p>
            <span className={`badge id-${id.status}`}>{humanize(id.status)}</span>{" "}
            {id.client_id && <strong>{id.client_id}</strong>} <span className="muted">confidence {percent(id.confidence)}</span>
          </p>
          {id.corrected_cnp && <p>Corrected CNP: <code>{id.corrected_cnp}</code></p>}
          <p>{id.reasoning}</p>
          {id.candidates?.length > 0 && (
            <ul>{id.candidates.map((c: any) => <li key={c.client_id}><strong>{c.client_id}</strong>: {c.reason}</li>)}</ul>
          )}
        </Card>
      )}

      {legal && (
        <Card title="3 · Legal decision (Legal Agent)">
          <p>
            <span className="badge">{humanize(legal.decision, DECISION)}</span>{" "}
            {legal.claim_type && <span className="pill">{humanize(legal.claim_type, CLAIM_LABEL)}</span>}
          </p>
          <p>{legal.summary}</p>
          {legal.legal_basis?.length > 0 && (
            <ul className="legal">{legal.legal_basis.map((t: string, i: number) => <li key={i}>{t}</li>)}</ul>
          )}
        </Card>
      )}

      {plan && (
        <Card title="Hold plan (deterministic rules engine)">
          <ol className="explain">{plan.explanation.map((l: string, i: number) => <li key={i}>{l}</li>)}</ol>
          <table className="grid">
            <thead>
              <tr><th>Garnishment</th><th>Type</th><th>Rank</th><th>Requested</th><th>Allocated</th><th>Outstanding</th></tr>
            </thead>
            <tbody>
              {plan.garnishments.map((g: any) => (
                <tr key={g.id}>
                  <td>{g.id === "NEW" ? "New order" : g.id}</td><td>{g.claim_label}</td><td>{g.rank}</td>
                  <td>{fmtMoney(g.requested_ron)}</td><td><strong>{fmtMoney(g.allocated_ron)}</strong></td>
                  <td className={g.remaining_ron > 0 ? "warn" : ""}>{fmtMoney(g.remaining_ron)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {plan.holds.length > 0 && (
            <table className="grid">
              <thead><tr><th>Account</th><th>Garnishment</th><th>Amount held</th><th>RON equivalent</th></tr></thead>
              <tbody>
                {plan.holds.map((h: any, i: number) => (
                  <tr key={i}>
                    <td><code>{h.iban}</code></td><td>{h.garnishment_id === "NEW" ? "New order" : h.garnishment_id}</td>
                    <td>{fmtMoney(h.amount, h.currency)}</td><td>{fmtMoney(h.amount_ron)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted small">
            Exchange rate: {show(plan.fx?.date)} ({show(plan.fx?.source)}). {plan.disclaimer}
          </p>
        </Card>
      )}

      {(actions || letter || registered || applied || release) && (
        <Card title="4 · Actions executed (Action Agent)">
          <ul>
            {registered && <li>Garnishment registered in core banking as <strong>{registered.id}</strong>.</li>}
            {applied && <li>Hold plan applied: {fmtMoney(applied.total_ron)} held in {applied.holds?.length ?? 0} hold(s).</li>}
            {release && (
              <li>
                Garnishment <strong>{release.garnishment?.id}</strong> released; {release.released_holds?.length ?? 0} hold(s) unblocked.
              </li>
            )}
            {letter && (
              <li>
                Reply letter <strong>{letter.reference}</strong> ({humanize(letter.type, LETTER)}) addressed to {show(letter.recipient)}.
                The official letter is written in Romanian.
              </li>
            )}
          </ul>
          {actions?.summary && <p>{actions.summary}</p>}
          {actions?.issues?.length > 0 && (
            <ul className="issues">{actions.issues.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul>
          )}
        </Card>
      )}

      {others.map(([k, v]) => (
        <Card key={k} title={humanize(k)}>
          <pre>{JSON.stringify(v, null, 2)}</pre>
        </Card>
      ))}

      {!Object.keys(data).length && <p className="muted">No data yet. The agents fill in the case data as they work.</p>}
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
