import { useRef, useState } from "react";
import { api, CaseSummary } from "../api";

export default function UploadZone({ onCreated }: { onCreated: (c: CaseSummary) => void }) {
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    try {
      for (const f of Array.from(files)) onCreated(await api.upload(f));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  return (
    <section
      className={`upload ${over ? "over" : ""} ${busy ? "busy" : ""}`}
      onClick={() => input.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        upload(e.dataTransfer.files);
      }}
      role="button"
      tabIndex={0}
      aria-label="Upload garnishment orders"
    >
      <svg className="upload-icon" viewBox="0 0 48 48" width="52" height="52" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M14 34h-2a8 8 0 0 1-1-15.9A11 11 0 0 1 32.5 15 9 9 0 0 1 36 34h-2" />
        <path d="M24 40V22M17 29l7-7 7 7" />
      </svg>
      <h2>Upload garnishment orders</h2>
      <p>Drag and drop PDF files here, or click to browse. Text and scanned documents are both supported.</p>
      <span className="btn primary">{busy ? "Uploading…" : "Choose files"}</span>
      {error && <p className="err small">{error}</p>}
      <input ref={input} type="file" accept="application/pdf" multiple hidden onChange={(e) => upload(e.target.files)} />
    </section>
  );
}
