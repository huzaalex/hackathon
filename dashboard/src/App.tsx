import { useCallback, useEffect, useState } from "react";
import { api, CaseSummary } from "./api";
import Sidebar from "./components/Sidebar";
import CaseList from "./components/CaseList";
import CaseView from "./components/CaseView";

export default function App() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [model, setModel] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setCases(await api.cases());
      setError(null);
    } catch {
      setError("The orchestrator is not responding. Is `docker compose up` running?");
    }
  }, []);

  useEffect(() => {
    api.health().then((h) => setModel(h.model)).catch(() => undefined);
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [refresh]);

  const onCreated = (c: CaseSummary) => {
    setSelected(c.id);
    refresh();
  };

  const onReset = async () => {
    if (!confirm("Reset the demo data (bank and cases)?")) return;
    await api.reset();
    setSelected(null);
    refresh();
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">GA</span>
          <div>
            <h1>Garnishment Agent</h1>
            <p>Autonomous processing of garnishment orders · Banca Demo S.A.</p>
          </div>
        </div>
        <div className="topbar-right">
          {model && <span className="pill">LLM: {model}</span>}
          <button className="btn ghost" onClick={onReset}>Reset demo</button>
        </div>
      </header>
      {error && <div className="banner error">{error}</div>}
      <main className="layout">
        <Sidebar onCreated={onCreated} />
        <CaseList cases={cases} selected={selected} onSelect={setSelected} />
        <section className="detail">
          {selected ? <CaseView key={selected} caseId={selected} /> : <EmptyState />}
        </section>
      </main>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="empty">
      <h2>Pick a scenario or upload a garnishment order</h2>
      <p>
        The supervisor plans the steps, delegates to specialised agents (reader, identification, legal, action) and only
        asks a human operator when it is not sure. Every legal calculation is done by a deterministic rules engine.
      </p>
    </div>
  );
}
