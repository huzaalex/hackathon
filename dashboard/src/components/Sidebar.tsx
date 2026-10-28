import { useEffect, useRef, useState } from "react";
import { api, CaseSummary, ClientRow, fmtMoney, Scenario } from "../api";

export default function Sidebar({ onCreated }: { onCreated: (c: CaseSummary) => void }) {
  const [samples, setSamples] = useState<Scenario[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.samples().then(setSamples).catch(() => setSamples([]));
  }, []);

  const run = async (file: string) => {
    setBusy(file);
    try {
      onCreated(await api.runSample(file));
    } finally {
      setBusy(null);
    }
  };

  const upload = async (files: FileList | null) => {
    if (!files) return;
    for (const f of Array.from(files)) onCreated(await api.upload(f));
  };

  return (
    <aside className="sidebar">
      <div
        className={`dropzone ${dragOver ? "over" : ""}`}
        onClick={() => fileInput.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          upload(e.dataTransfer.files);
        }}
      >
        <strong>Upload garnishment orders</strong>
        <span>PDF (text or scanned) · click or drag &amp; drop</span>
        <input ref={fileInput} type="file" accept="application/pdf" multiple hidden onChange={(e) => upload(e.target.files)} />
      </div>

      <h3>Demo scenarios</h3>
      <ul className="scenarios">
        {samples.map((s) => (
          <li key={s.file}>
            <div className="scenario-head">
              <strong>{s.title}</strong>
              <button className="btn small" disabled={busy === s.file} onClick={() => run(s.file)}>Run</button>
            </div>
            <p>{s.description}</p>
            <p className="expected">Expected: {s.expected}</p>
            <a className="link" href={`/api/samples/${s.file}`} target="_blank" rel="noreferrer">View PDF (Romanian original)</a>
          </li>
        ))}
        {!samples.length && <li className="muted">No scenarios found (did the data generator run?)</li>}
      </ul>

      <IncomingForm />
    </aside>
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
        ? `New balance ${fmtMoney(r.new_balance)}. The client has active garnishments, so the agent was notified.`
        : `New balance ${fmtMoney(r.new_balance)}. No active garnishments, nothing to do.`);
    } catch (e) {
      setMsg(String(e));
    }
  };

  return (
    <div className="incoming">
      <h3>Simulate an incoming payment</h3>
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
      <button className="btn" onClick={submit} disabled={!iban}>Send payment</button>
      {msg && <p className="muted small">{msg}</p>}
    </div>
  );
}
