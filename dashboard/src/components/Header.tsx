import { CaseSummary } from "../api";
import DemosMenu from "./DemosMenu";

export type Theme = "light" | "dark";

interface Props {
  theme: Theme;
  onToggleTheme: () => void;
  onReset: () => void;
  onCreated: (c: CaseSummary) => void;
}

export default function Header({ theme, onToggleTheme, onReset, onCreated }: Props) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="logo" aria-hidden>G</span>
        <span className="brand-name">Garnishment Agent</span>
        <span className="brand-bank">Banca Demo S.A.</span>
      </div>
      <nav className="topbar-right" aria-label="Main">
        <DemosMenu onCreated={onCreated} />
        <button className="btn ghost" onClick={onReset}>Reset Demo</button>
        <button
          className="icon-btn theme-toggle"
          onClick={onToggleTheme}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          title={theme === "dark" ? "Light mode" : "Dark mode"}
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
      </nav>
    </header>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden>
      <path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z" />
    </svg>
  );
}
