export const API = "/api";

export type CaseStatus = "QUEUED" | "RUNNING" | "NEEDS_REVIEW" | "DONE" | "FAILED";

export interface CaseSummary {
  id: string;
  kind: "DOCUMENT" | "EVENT";
  title: string;
  created_at: string;
  status: CaseStatus;
  outcome: string | null;
  document_name: string | null;
  client_id: string | null;
  processing_seconds: number;
  operator_interventions: number;
  cost_usd: number;
}

export interface Metrics {
  cases_done: number;
  in_progress: number;
  automated: number;
  automation_rate: number | null;
  avg_processing_seconds: number | null;
  avg_cost_usd: number | null;
  total_cost_usd: number;
  manual_minutes_saved: number;
  frauds_stopped: number;
  assumptions: {
    manual_minutes_per_case: number;
    operator_minutes_per_review: number;
    price_input_per_mtok: number;
    price_output_per_mtok: number;
    model: string;
  };
}

export interface EvalCheck {
  name: string;
  passed: boolean;
  expected: string | number;
  actual: string | number;
}

export interface EvalItem {
  file: string;
  title: string;
  status: "PENDING" | "RUNNING" | "PASS" | "FAIL" | "ERROR" | "TIMEOUT";
  case_id: string | null;
  checks: EvalCheck[];
  operator_questions: { question: string; answer: string }[];
  outcome?: string | null;
  processing_seconds?: number;
  cost_usd?: number;
  llm_calls?: number;
  operator_interventions?: number;
}

export interface EvalSummary {
  completed: number;
  total: number;
  scenarios_passed?: number;
  outcome_accuracy?: number;
  checks_passed?: number;
  checks_total?: number;
  automation_rate?: number;
  avg_processing_seconds?: number;
  avg_cost_usd?: number;
  total_cost_usd?: number;
  total_llm_calls?: number;
}

export interface EvalState {
  status: "IDLE" | "RUNNING" | "DONE" | "FAILED";
  started_at: string | null;
  finished_at: string | null;
  items: EvalItem[];
  summary: EvalSummary | null;
  error: string | null;
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
  metrics: () => request<Metrics>("/metrics"),
  evalStatus: () => request<EvalState>("/eval/status"),
  evalRun: () => request<EvalState>("/eval/run", { method: "POST" }),
};

export const fmtDuration = (s: number | null | undefined) => {
  if (s == null) return "-";
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${Math.round(s % 60)}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
};

export const fmtUsd = (x: number | null | undefined) => (x == null ? "-" : `$${x.toFixed(x < 1 ? 3 : 2)}`);
export const fmtPct = (x: number | null | undefined) => (x == null ? "-" : `${Math.round(x * 100)}%`);

export const fmtMoney = (x: number | null | undefined, currency = "RON") =>
  x == null ? "-" : `${x.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;

export const STATUS_LABEL: Record<CaseStatus, string> = {
  QUEUED: "Queued",
  RUNNING: "Running",
  NEEDS_REVIEW: "Needs operator",
  DONE: "Done",
  FAILED: "Failed",
};

export const OUTCOME_LABEL: Record<string, string> = {
  GARNISHMENT_APPLIED_FULL: "Garnishment applied in full",
  GARNISHMENT_APPLIED_PARTIAL: "Garnishment applied partially",
  NO_FUNDS: "No funds - active on future credits",
  DEBTOR_NOT_CLIENT: "Debtor is not a client",
  DUPLICATE: "Duplicate - ignored",
  GARNISHMENT_RELEASED: "Garnishment released",
  REEVALUATION_APPLIED: "Holds re-evaluated",
  REJECTED_BY_OPERATOR: "Rejected by operator",
  DOCUMENT_NOT_PROCESSABLE: "Document not processable",
  SUSPECTED_FRAUD: "Suspected fraud - blocked",
};

export const CLAIM_LABEL: Record<string, string> = {
  CHILD_SUPPORT: "Child support",
  WAGE: "Wage claim",
  TAX: "Tax claim",
  UNSECURED: "Other (unsecured) claim",
  UNKNOWN: "Unknown",
};

export const SOURCE_LABEL: Record<string, string> = {
  SALARY: "Salary",
  PENSION: "Pension",
  CHILD_ALLOWANCE: "Child allowance",
  SOCIAL_BENEFIT: "Social benefit",
  CHILDCARE_BENEFIT: "Childcare benefit",
  TRANSFER: "Transfer",
  PAYMENT: "Payment",
};

/** Turns ENUM_LIKE_CODES into "Enum like codes" when no explicit label exists. */
export const humanize = (code: string | null | undefined, labels?: Record<string, string>) => {
  if (!code) return "-";
  if (labels?.[code]) return labels[code];
  const s = code.toLowerCase().replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
};
