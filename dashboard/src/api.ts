export const API = "/api";

export type CaseStatus = "IN_ASTEPTARE" | "IN_LUCRU" | "NECESITA_OPERATOR" | "FINALIZAT" | "EROARE";

export interface CaseSummary {
  id: string;
  kind: "DOCUMENT" | "EVENIMENT";
  title: string;
  created_at: string;
  status: CaseStatus;
  outcome: string | null;
  document_name: string | null;
  client_id: string | null;
}

export interface Review {
  question: string;
  options: string[];
  context: string;
}

export interface CaseDetail extends CaseSummary {
  summary: string | null;
  blackboard: Record<string, any>;
  review: Review | null;
  trigger: Record<string, any> | null;
  has_response_pdf: boolean;
  has_document: boolean;
  usage: { llm_calls: number; input_tokens: number; output_tokens: number };
}

export interface AgentEvent {
  seq: number;
  ts: string;
  agent: string;
  type: string;
  data: Record<string, any>;
}

export interface Scenario {
  file: string;
  title: string;
  description: string;
  expected: string;
}

export interface Account {
  iban: string;
  currency: string;
  product: string;
  status: string;
  balance: number;
}

export interface ClientRow {
  id: string;
  full_name: string;
  cnp: string;
  address: string;
  accounts: Account[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API + path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<{ model: string; region: string }>("/health"),
  cases: () => request<CaseSummary[]>("/cases"),
  caseDetail: (id: string) => request<CaseDetail>(`/cases/${id}`),
  samples: () => request<Scenario[]>("/samples"),
  runSample: (file: string) => request<CaseSummary>("/cases/from-sample", json({ file })),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<CaseSummary>("/cases", { method: "POST", body: fd });
  },
  review: (id: string, answer: string) => request<CaseSummary>(`/cases/${id}/review`, json({ answer })),
  clients: () => request<ClientRow[]>("/demo/clients"),
  client: (id: string) => request<any>(`/demo/clients/${id}`),
  incoming: (iban: string, amount: number, source: string) => request<any>("/demo/incoming", json({ iban, amount, source })),
  reset: () => request<any>("/demo/reset", { method: "POST" }),
};

export const fmtMoney = (x: number | null | undefined, currency = "RON") =>
  x == null ? "–" : `${x.toLocaleString("ro-RO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;

export const STATUS_LABEL: Record<CaseStatus, string> = {
  IN_ASTEPTARE: "În așteptare",
  IN_LUCRU: "În lucru",
  NECESITA_OPERATOR: "Necesită operator",
  FINALIZAT: "Finalizat",
  EROARE: "Eroare",
};

export const OUTCOME_LABEL: Record<string, string> = {
  POPRIRE_APLICATA_INTEGRAL: "Poprire aplicată integral",
  POPRIRE_APLICATA_PARTIAL: "Poprire aplicată parțial",
  FARA_FONDURI: "Fără fonduri – activă pe încasări viitoare",
  DEBITOR_NECLIENT: "Debitorul nu este client",
  DUPLICAT: "Duplicat – ignorat",
  POPRIRE_RIDICATA: "Poprire ridicată",
  REEVALUARE_APLICATA: "Reevaluare aplicată",
  RESPINS_DE_OPERATOR: "Respins de operator",
  DOCUMENT_NEPROCESABIL: "Document neprocesabil",
};
