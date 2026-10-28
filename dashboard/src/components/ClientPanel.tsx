import { useEffect, useState } from "react";
import { api, fmtMoney } from "../api";

const SOURCE_LABEL: Record<string, string> = {
  SALARIU: "salariu", PENSIE: "pensie", ALOCATIE: "alocație", AJUTOR_SOCIAL: "ajutor social", TRANSFER: "transfer",
};

export default function ClientPanel({ clientId, version }: { clientId: string; version: number }) {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api.client(clientId).then(setData).catch(() => setData(null));
  }, [clientId, version]);

  if (!data) return <p className="muted">Se încarcă…</p>;
  const c = data.client;
  return (
    <div className="client-panel">
      <section className="card">
        <h4>{c.full_name} · {c.id}</h4>
        <p className="muted">CNP {c.cnp} · {c.address}</p>
      </section>
      <section className="card">
        <h4>Conturi (încasări din ultimele {data.window_days} zile)</h4>
        <table className="grid">
          <thead><tr><th>IBAN</th><th>Produs</th><th>Status</th><th>Sold</th><th>Blocat</th><th>Disponibil</th><th>Încasări</th></tr></thead>
          <tbody>
            {data.accounts.map((a: any) => (
              <tr key={a.iban} className={a.status !== "ACTIVE" ? "dim" : ""}>
                <td><code>{a.iban}</code></td><td>{a.product}</td><td>{a.status}</td>
                <td>{fmtMoney(a.balance, a.currency)}</td>
                <td className={a.held > 0 ? "warn" : ""}>{fmtMoney(a.held, a.currency)}</td>
                <td>{fmtMoney(a.available, a.currency)}</td>
                <td className="small">
                  {Object.entries(a.inflows).map(([s, v]) => `${SOURCE_LABEL[s] ?? s}: ${fmtMoney(v as number, a.currency)}`).join(" · ") || "–"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h4>Popriri</h4>
        <table className="grid">
          <thead><tr><th>ID</th><th>Dosar</th><th>Emitent</th><th>Tip</th><th>Total</th><th>Blocat acum</th><th>Status</th></tr></thead>
          <tbody>
            {data.garnishments.map((g: any) => (
              <tr key={g.id} className={g.status !== "ACTIVE" ? "dim" : ""}>
                <td>{g.id}</td><td>{g.case_ref}</td><td>{g.issuer_name}</td><td>{g.claim_type}</td>
                <td>{fmtMoney(g.total_amount)}</td><td>{fmtMoney(g.held_ron)}</td><td>{g.status}</td>
              </tr>
            ))}
            {!data.garnishments.length && <tr><td colSpan={7} className="muted">Nicio poprire</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
