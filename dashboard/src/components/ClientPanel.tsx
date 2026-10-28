import { useEffect, useState } from "react";
import { api, CLAIM_LABEL, fmtMoney, humanize, SOURCE_LABEL } from "../api";

const STATUS: Record<string, string> = { ACTIVE: "Active", CLOSED: "Closed", LIFTED: "Released", SATISFIED: "Satisfied" };

export default function ClientPanel({ clientId, version }: { clientId: string; version: number }) {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api.client(clientId).then(setData).catch(() => setData(null));
  }, [clientId, version]);

  if (!data) return <p className="muted">Loading…</p>;
  const c = data.client;
  return (
    <div className="client-panel">
      <section className="card">
        <h4>{c.full_name} · {c.id}</h4>
        <p className="muted">CNP {c.cnp} · {c.address}</p>
      </section>
      <section className="card">
        <h4>Accounts (credits of the last {data.window_days} days)</h4>
        <table className="grid">
          <thead><tr><th>IBAN</th><th>Product</th><th>Status</th><th>Balance</th><th>Held</th><th>Available</th><th>Recent credits</th></tr></thead>
          <tbody>
            {data.accounts.map((a: any) => (
              <tr key={a.iban} className={a.status !== "ACTIVE" ? "dim" : ""}>
                <td><code>{a.iban}</code></td><td>{a.product}</td><td>{humanize(a.status, STATUS)}</td>
                <td>{fmtMoney(a.balance, a.currency)}</td>
                <td className={a.held > 0 ? "warn" : ""}>{fmtMoney(a.held, a.currency)}</td>
                <td>{fmtMoney(a.available, a.currency)}</td>
                <td className="small">
                  {Object.entries(a.inflows).map(([s, v]) => `${humanize(s, SOURCE_LABEL)}: ${fmtMoney(v as number, a.currency)}`).join(" · ") || "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h4>Garnishments</h4>
        <table className="grid">
          <thead><tr><th>ID</th><th>Case number</th><th>Issuer</th><th>Claim type</th><th>Total</th><th>Currently held</th><th>Status</th></tr></thead>
          <tbody>
            {data.garnishments.map((g: any) => (
              <tr key={g.id} className={g.status !== "ACTIVE" ? "dim" : ""}>
                <td>{g.id}</td><td>{g.case_ref}</td><td>{g.issuer_name}</td><td>{humanize(g.claim_type, CLAIM_LABEL)}</td>
                <td>{fmtMoney(g.total_amount)}</td><td>{fmtMoney(g.held_ron)}</td><td>{humanize(g.status, STATUS)}</td>
              </tr>
            ))}
            {!data.garnishments.length && <tr><td colSpan={7} className="muted">No garnishments</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
