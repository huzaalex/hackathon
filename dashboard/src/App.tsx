import { useCallback, useEffect, useRef, useState } from "react";
import { api, CaseSummary } from "./api";
import { loadPref, savePref } from "./prefs";
import Header, { Theme } from "./components/Header";
import CasesSidebar from "./components/CasesSidebar";
import UploadZone from "./components/UploadZone";
import Steps from "./components/Steps";
import CaseView from "./components/CaseView";

const initialTheme = (): Theme =>
  (document.documentElement.dataset.theme as Theme) ||
  (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light");

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [casesOpen, setCasesOpen] = useState<boolean>(() => loadPref("cases-open", window.innerWidth > 1000) === true);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [model, setModel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const detailRef = useRef<HTMLElement>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    savePref("theme", theme);
  }, [theme]);

  useEffect(() => savePref("cases-open", casesOpen), [casesOpen]);

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

  const openCase = (id: string) => {
    setSelected(id);
    if (window.innerWidth <= 900) setCasesOpen(false); // the drawer covers the page on small screens
    requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const onCreated = (c: CaseSummary) => {
    refresh();
    openCase(c.id);
  };

  const onReset = async () => {
    if (!confirm("Reset the demo data (bank and cases)?")) return;
    await api.reset();
    setSelected(null);
    refresh();
  };

  const selectedCase = cases.find((c) => c.id === selected) ?? null;

  return (
    <div className="app">
      <Header theme={theme} onToggleTheme={() => setTheme(theme === "dark" ? "light" : "dark")} onReset={onReset} onCreated={onCreated} />

      <CasesSidebar
        open={casesOpen}
        onToggle={() => setCasesOpen(!casesOpen)}
        cases={cases}
        selected={selected}
        onSelect={openCase}
      />

      <main className={`main ${casesOpen ? "shifted" : ""}`}>
        {error && <div className="banner error">{error}</div>}
        <div className="container">
          <section className="hero">
            <p className="eyebrow">Back-office automation</p>
            <h1>Autonomous processing of garnishment orders</h1>
          </section>

          <UploadZone onCreated={onCreated} />
          <Steps status={selectedCase?.status ?? null} />

          <section className="detail-section" ref={detailRef} aria-label="Case details">
            {selected ? (
              <CaseView key={selected} caseId={selected} />
            ) : (
              <div className="empty">
                <h2>No case selected</h2>
                <p>
                  Upload a garnishment order or pick a scenario from <strong>Demos</strong>. The agents' reasoning appears
                  here live. Earlier cases are in the <strong>Cases</strong> panel on the left.
                </p>
              </div>
            )}
          </section>

          <footer className="footer">
            {model ? `Agents powered by ${model} on Amazon Bedrock. ` : ""}
            All legal calculations are made by a deterministic rules engine.
          </footer>
        </div>
      </main>
    </div>
  );
}
