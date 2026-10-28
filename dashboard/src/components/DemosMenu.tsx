import { useEffect, useRef, useState } from "react";
import { api, CaseSummary, ClientRow, fmtMoney, Scenario } from "../api";

export default function DemosMenu({ onCreated }: { onCreated: (c: CaseSummary) => void }) {
  const [open, setOpen] = useState(false);
  const [samples, setSamples] = useState<Scenario[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.samples().then(setSamples).catch(() => setSamples([]));
  }, []);

  // Close on outside click or Escape
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const run = async (file: string) => {
    setBusy(file);
    try {
      onCreated(await api.runSample(file));
      setOpen(false);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="menu" ref={root}>
      <button className={`btn menu-trigger ${open ? "on" : ""}`} aria-haspopup="true" aria-expanded={open} onClick={() => setOpen(!open)}>
        Demos
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="menu-panel" role="menu">
          <div className="menu-section">
            <h3>Demo scenarios</h3>
            <p className="muted small">Each scenario sends a real Romanian garnishment PDF through the agents.</p>
            <ul className="scenario-list">
              {samples.map((s, i) => (
                <li key={s.file}>
                  <button role="menuitem" className="scenario-item" disabled={busy !== null} onClick={() => run(s.file)}>
                    <span className="scenario-num">{String(i + 1).padStart(2, "0")}</span>
                    <span className="scenario-body">
                      <strong>{s.title}</strong>
                      <span>{s.description}</span>
                      <span className="expected">Expected: {s.expected}</span>
                    </span>
                    <span className="scenario-run">{busy === s.file ? "Starting…" : "Run"}</span>
                  </button>
                  <a className="link small" href={`/api/samples/${s.file}`} target="_blank" rel="noreferrer">
                    View PDF (Romanian original)
                  </a>
                </li>
              ))}
              {!samples.length && <li className="muted">No scenarios found (did the data generator run?)</li>}
            </ul>
          </div>
          <div className="menu-section">
            <IncomingForm />
          </div>
        </div>
      )}
    </div>
  );
}

function IncomingForm() {
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [iban, setIban] = useState("");
  const [amount, setAmount] = useState("5000");
  const [source, setSource] = useState("SALARY");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api.clients().then((cs) => {
      setClients(cs);
      const mihai = cs.find((c) => c.id === "CL009");
      if (mihai?.accounts[0]) setIban(mihai.accounts[0].iban);
    }).catch(() => undefined);
  }, []);

  const submit = async () => {
    try {
      const r = await api.incoming(iban, Number(amount), source);
      setMsg(r.orchestrator_notified
        ? `New balance ${fmtMoney(r.new_balance)}. The client has active garnishments, so the agents were notified (new Event case).`
        : `New balance ${fmtMoney(r.new_balance)}. No active garnishments, nothing to do.`);
    } catch (e) {
      setMsg(String(e));
    }
  };

  return (
    <div className="incoming">
      <h3>Simulate an incoming payment</h3>
      <p className="muted small">
        Money arriving for a debtor with an active garnishment wakes the agents up automatically (try it after scenario 09).
      </p>
      <label>
        Account
        <select value={iban} onChange={(e) => setIban(e.target.value)}>
          {clients.flatMap((c) =>
            c.accounts.filter((a) => a.status === "ACTIVE").map((a) => (
              <option key={a.iban} value={a.iban}>
                {c.id} {c.full_name} · {a.currency} · {fmtMoney(a.balance, a.currency)}
              </option>
            )),
          )}
        </select>
      </label>
      <div className="row">
        <label>
          Amount
          <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <label>
          Source
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="SALARY">Salary</option>
            <option value="PENSION">Pension</option>
            <option value="CHILD_ALLOWANCE">Child allowance</option>
            <option value="TRANSFER">Transfer</option>
          </select>
        </label>
      </div>
      <button className="btn primary" onClick={submit} disabled={!iban}>Send payment</button>
      {msg && <p className="muted small">{msg}</p>}
    </div>
  );
}
