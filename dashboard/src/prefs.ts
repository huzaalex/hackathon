// Per-viewer UI preferences (theme, sidebar). Storage can be unavailable (private mode, blocked site data),
// so every access is guarded and the UI falls back to defaults.
const PREFIX = "ga-";

export function loadPref<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function savePref(key: string, value: unknown) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}
