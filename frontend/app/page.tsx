"use client";

import dynamic from "next/dynamic";
import type { Data, Layout } from "plotly.js";
import type { PlotParams } from "react-plotly.js";
import { useEffect, useMemo, useState } from "react";
import { Check, Database, Download, History, LoaderCircle, Play, RefreshCw, Send, ShieldCheck, X } from "lucide-react";
import { API_URL, HistoryItem, QueryDraft, QueryResult, api } from "@/lib/api";

const Plot = dynamic<PlotParams>(() => import("react-plotly.js"), { ssr: false });

const fallbackQuestions = [
  "What is total revenue by month in 2026?",
  "Which products generated the most revenue?",
  "Show revenue by region.",
  "What is average order value by customer segment?",
  "Which customers have pending or failed payments?",
  "Which product categories produce the highest gross margin?",
  "Break down revenue by payment method.",
  "Show last month revenue by region.",
  "Who are our repeat customers by total spend?",
  "Which sales managers own the most revenue?"
];

type BusyAction = "generating" | "executing" | "rejecting" | null;

export default function Home() {
  const [sessionId, setSessionId] = useState("");
  const [question, setQuestion] = useState(fallbackQuestions[0]);
  const [draft, setDraft] = useState<QueryDraft | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [demoQuestions, setDemoQuestions] = useState<string[]>(fallbackQuestions);
  const [editedSql, setEditedSql] = useState("");
  const [booting, setBooting] = useState(true);
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [error, setError] = useState("");
  const [demoMode, setDemoMode] = useState(true);
  const loading = busyAction !== null;
  const isGenerating = busyAction === "generating";
  const isExecuting = busyAction === "executing";

  useEffect(() => {
    async function boot() {
      try {
        const [health, session, questions] = await Promise.all([
          api.health(),
          api.createSession(),
          api.demoQuestions().catch(() => ({ questions: fallbackQuestions }))
        ]);
        setDemoMode(health.demo_mode || session.demo_mode);
        setSessionId(session.session_id);
        setDemoQuestions(questions.questions);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to reach backend.");
      } finally {
        setBooting(false);
      }
    }
    boot();
  }, []);

  async function refreshHistory(activeSession = sessionId) {
    if (!activeSession) return;
    const rows = await api.history(activeSession);
    setHistory(rows);
  }

  function clearGeneratedState() {
    setDraft(null);
    setResult(null);
    setEditedSql("");
    setError("");
  }

  async function submitQuestion(nextQuestion = question) {
    if (!sessionId || !nextQuestion.trim()) return;
    setBusyAction("generating");
    setError("");
    setDraft(null);
    setResult(null);
    setEditedSql("");
    try {
      const response = await api.ask(sessionId, nextQuestion.trim());
      setDraft(response);
      setEditedSql(response.generated_sql || "");
      await refreshHistory(response.session_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate SQL.");
    } finally {
      setBusyAction(null);
    }
  }

  async function approve() {
    if (!draft) return;
    setBusyAction("executing");
    setError("");
    setResult(null);
    try {
      const response = await api.approve(draft.query_id);
      setResult(response);
      await refreshHistory(response.session_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to execute SQL.");
    } finally {
      setBusyAction(null);
    }
  }

  async function submitEdit() {
    if (!draft) return;
    setBusyAction("executing");
    setError("");
    setResult(null);
    try {
      const response = await api.edit(draft.query_id, editedSql, "Reviewer edited SQL before execution.");
      setResult(response);
      await refreshHistory(response.session_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to execute edited SQL.");
    } finally {
      setBusyAction(null);
    }
  }

  async function reject() {
    if (!draft) return;
    setBusyAction("rejecting");
    setError("");
    try {
      await api.reject(draft.query_id, "Reviewer rejected generated SQL.");
      setDraft(null);
      setResult(null);
      await refreshHistory(sessionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reject SQL.");
    } finally {
      setBusyAction(null);
    }
  }

  const chart = result?.plotly_json;
  const hasRows = Boolean(result?.rows?.length);
  const pngUrl = useMemo(() => (result ? `${API_URL}/chart/${result.query_id}?format=png` : ""), [result]);
  const draftHasIssue = Boolean(
    draft?.error || ["generation_failed", "validation_failed"].includes(draft?.status || "")
  );
  const resultHasIssue = Boolean(
    result?.error || ["execution_failed", "validation_failed"].includes(result?.status || "")
  );
  const queryHasIssue = draftHasIssue || resultHasIssue;
  const canRunSql = Boolean(draft && editedSql.trim() && !loading && !draftHasIssue);

  if (booting) {
    return (
      <main className="startup-screen">
        <section className="startup-panel" aria-live="polite">
          <div className="startup-icon">
            <LoaderCircle size={34} />
          </div>
          <p className="eyebrow">Please wait</p>
          <h1>Loading in progress</h1>
          <p>
            The backend is hosted on free Render, so the first request can take 30-60 seconds while the service wakes up.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Database size={24} />
          <div>
            <h1>Agentic Text-to-SQL</h1>
            <p>LangGraph workflow with review and dashboards</p>
          </div>
        </div>

        <div className={demoMode ? "mode mode-demo" : "mode"}>
          <ShieldCheck size={18} />
          <span>{demoMode ? "Demo Mode" : "Protected LLM Mode"}</span>
        </div>

        <section className="panel">
          <div className="panel-title">
            <Play size={17} />
            Demo Questions
          </div>
          <div className="question-list">
            {demoQuestions.map((item) => (
              <button
                key={item}
                type="button"
                className="question-chip"
                disabled={loading}
                onClick={() => {
                  setQuestion(item);
                  clearGeneratedState();
                }}
              >
                {item}
              </button>
            ))}
          </div>
        </section>

        <section className="panel history-panel">
          <div className="panel-title">
            <History size={17} />
            Query History
          </div>
          <div className="history-list">
            {history.length === 0 && <p className="muted">No reviewed queries yet.</p>}
            {history.map((item) => (
              <button
                key={item.query_id}
                type="button"
                className="history-item"
                disabled={loading}
                onClick={() => {
                  setQuestion(item.question);
                  setDraft(null);
                  setResult(null);
                  setError("");
                  setEditedSql(item.final_sql || item.generated_sql || "");
                }}
              >
                <span>{item.question}</span>
                <small>{item.status}</small>
              </button>
            ))}
          </div>
        </section>
      </aside>

      <section className="workspace">
        <div className="topbar">
          <div>
            <p className="eyebrow">Human-reviewed analytics agent</p>
            <h2>Ask a business question, inspect the SQL, then approve execution.</h2>
          </div>
          <button className="ghost" type="button" onClick={() => void refreshHistory()} title="Refresh history">
            <RefreshCw size={18} />
            Refresh
          </button>
        </div>

        <section className="ask-panel">
          <textarea
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
              clearGeneratedState();
            }}
            placeholder="Ask about revenue, customers, products, regions, or payments..."
          />
          <button type="button" className="primary" onClick={() => void submitQuestion()} disabled={loading || !sessionId}>
            {isGenerating ? <LoaderCircle className="inline-spinner" size={18} /> : <Send size={18} />}
            {isGenerating ? "Generating" : "Generate SQL"}
          </button>
        </section>

        {error && <div className="error">{error}</div>}

        <div className="grid">
          <section className="panel sql-panel">
            <div className="section-heading">
              <span>SQL Preview</span>
              <small>{isGenerating ? "generating" : draft?.status || "waiting"}</small>
            </div>
            <div className="sql-editor-wrap">
              {isGenerating && (
                <div className="sql-loading" aria-live="polite">
                  <LoaderCircle size={20} />
                  <span>Generating SQL query...</span>
                </div>
              )}
              <textarea
                className="sql-editor"
                value={editedSql}
                onChange={(event) => setEditedSql(event.target.value)}
                spellCheck={false}
                readOnly={isGenerating}
                placeholder={isGenerating ? "" : "Generated SQL will appear here."}
              />
            </div>
            <div className="review-actions">
              <button type="button" className="approve" onClick={() => void approve()} disabled={!canRunSql}>
                <Check size={18} />
                Approve
              </button>
              <button type="button" className="secondary" onClick={() => void submitEdit()} disabled={!canRunSql}>
                <Play size={18} />
                Run Edit
              </button>
              <button type="button" className="reject" onClick={() => void reject()} disabled={!draft || loading}>
                <X size={18} />
                Reject
              </button>
            </div>
            {draft?.error && <p className="warning">{draft.error}</p>}
          </section>

          <section className="panel">
            <div className="section-heading">
              <span>Execution Result</span>
              <small>{isExecuting ? "running" : result?.status || "not run"}</small>
            </div>
            {isExecuting ? (
              <div className="empty loading-empty">
                <LoaderCircle size={20} />
                <span>Executing approved query...</span>
              </div>
            ) : queryHasIssue ? (
              <div className="empty result-error">
                Please regenerate the query as there are some errors in the question.
              </div>
            ) : hasRows ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>{result?.columns.map((column) => <th key={column}>{column}</th>)}</tr>
                  </thead>
                  <tbody>
                    {result?.rows.slice(0, 12).map((row, index) => (
                      <tr key={`${result.query_id}-${index}`}>
                        {result.columns.map((column) => (
                          <td key={column}>{String(row[column] ?? "")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty">Approved query output will appear here.</div>
            )}
            {result?.error && <p className="warning">{result.error}</p>}
          </section>
        </div>

        <section className="panel chart-panel">
          <div className="section-heading">
            <span>Plotly Dashboard Panel</span>
            {result?.chart_png_available && (
              <a className="download" href={pngUrl} target="_blank" rel="noreferrer">
                <Download size={17} />
                PNG
              </a>
            )}
          </div>
          {chart?.data?.length ? (
            <Plot data={chart.data as Data[]} layout={chart.layout as Partial<Layout>} className="plot" />
          ) : (
            <div className="empty">Charts are generated after a reviewed query returns plottable data.</div>
          )}
        </section>
      </section>
    </main>
  );
}

