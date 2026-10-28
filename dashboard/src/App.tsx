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
    } catch (e) {
      setError("Orchestratorul nu răspunde – rulează `docker compose up`?");
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
    if (!confirm("Resetezi datele demo (bancă + cazuri)?")) return;
    await api.reset();
    setSelected(null);
    refresh();
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">§</span>
          <div>
            <h1>Poprire Agent</h1>
            <p>Procesare autonomă a adreselor de poprire · Banca Demo S.A.</p>
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
      <h2>Alege un scenariu sau încarcă o adresă de poprire</h2>
      <p>
        Supervizorul planifică pașii, deleagă agenților specializați (citire, identificare, juridic, acțiune) și
        cere ajutorul unui operator doar când nu e sigur. Toate calculele legale sunt făcute de un motor de reguli
        determinist.
      </p>
    </div>
  );
}
