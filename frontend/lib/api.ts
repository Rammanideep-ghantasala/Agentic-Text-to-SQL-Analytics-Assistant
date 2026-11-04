export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type HealthResponse = {
  status: string;
  demo_mode: boolean;
  llm_providers: {
    openai: boolean;
    ollama: boolean;
  };
};

export type QueryDraft = {
  query_id: string;
  session_id: string;
  question: string;
  resolved_question?: string;
  generated_sql?: string;
  status: string;
  requires_review: boolean;
  schema_context?: string;
  historical_context?: string;
  error?: string;
  demo_mode: boolean;
};

export type QueryResult = {
  query_id: string;
  session_id: string;
  question: string;
  generated_sql?: string;
  corrected_sql?: string;
  final_sql?: string;
  status: string;
  columns: string[];
  rows: Record<string, unknown>[];
  plotly_json?: {
    data?: unknown[];
    layout?: Record<string, unknown>;
    chart_type?: string;
  };
  chart_png_available: boolean;
  error?: string;
  latency_ms?: number;
};

export type HistoryItem = {
  query_id: string;
  question: string;
  generated_sql?: string;
  corrected_sql?: string;
  final_sql?: string;
  status: string;
  created_at: string;
  feedback?: string;
  error?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {})
    }
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  createSession: () => request<{ session_id: string; demo_mode: boolean }>("/sessions", { method: "POST" }),
  ask: (sessionId: string, question: string) =>
    request<QueryDraft>("/query", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, question })
    }),
  approve: (queryId: string) => request<QueryResult>(`/review/${queryId}/approve`, { method: "POST" }),
  edit: (queryId: string, sql: string, feedback?: string) =>
    request<QueryResult>(`/review/${queryId}/edit`, {
      method: "POST",
      body: JSON.stringify({ sql, feedback })
    }),
  reject: (queryId: string, feedback?: string) =>
    request<{ status: string; query_id: string }>(`/review/${queryId}/reject`, {
      method: "POST",
      body: JSON.stringify({ feedback })
    }),
  history: (sessionId: string) => request<HistoryItem[]>(`/history/${sessionId}`),
  demoQuestions: () => request<{ questions: string[] }>("/demo/questions")
};

