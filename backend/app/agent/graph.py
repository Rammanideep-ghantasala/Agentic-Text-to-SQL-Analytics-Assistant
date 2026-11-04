import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from sqlalchemy import select, text

from app.agent.llm import correct_sql as llm_correct_sql
from app.agent.llm import generate_sql as llm_generate_sql
from app.agent.rag import retrieve_historical_queries, retrieve_schema_context
from app.agent.sql import deterministic_sql_repair, validate_select_sql
from app.agent.visualization import generate_matplotlib_png, generate_plotly_json
from app.config import get_settings
from app.database import (
    ENGINE,
    app_sessions,
    from_json,
    get_db_session,
    get_session_memory,
    query_runs,
    rows_to_dicts,
    to_json,
    update_session_memory,
)


class AgentState(TypedDict, total=False):
    session_id: str
    query_id: str
    question: str
    resolved_question: str
    provider: Optional[str]
    schema_context: str
    historical_context: str
    memory: Dict[str, Any]
    generated_sql: Optional[str]
    corrected_sql: Optional[str]
    final_sql: Optional[str]
    status: str
    error: Optional[str]
    requires_review: bool
    rows: List[Dict[str, Any]]
    columns: List[str]
    plotly_json: Dict[str, Any]
    chart_png_base64: Optional[str]
    chart_hint: Optional[str]
    latency_ms: float


class TextToSQLAgent:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.engine = ENGINE
        self.review_graph = self._build_review_graph()
        self.execution_graph = self._build_execution_graph()

    def _build_review_graph(self) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph

            graph = StateGraph(AgentState)
            graph.add_node("understand_question", self.understand_question)
            graph.add_node("retrieve_schema_context", self.retrieve_schema_context)
            graph.add_node("retrieve_historical_queries", self.retrieve_historical_queries)
            graph.add_node("generate_sql", self.generate_sql)
            graph.add_node("validate_sql", self.validate_sql)
            graph.add_node("human_review", self.human_review)
            graph.add_node("store_history", self.store_history)

            graph.add_edge(START, "understand_question")
            graph.add_edge("understand_question", "retrieve_schema_context")
            graph.add_edge("retrieve_schema_context", "retrieve_historical_queries")
            graph.add_edge("retrieve_historical_queries", "generate_sql")
            graph.add_edge("generate_sql", "validate_sql")
            graph.add_edge("validate_sql", "human_review")
            graph.add_edge("human_review", "store_history")
            graph.add_edge("store_history", END)
            return graph.compile()
        except Exception:
            return None

    def _build_execution_graph(self) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph

            graph = StateGraph(AgentState)
            graph.add_node("execute_sql", self.execute_sql)
            graph.add_node("self_correct_sql", self.self_correct_sql)
            graph.add_node("generate_visualization", self.generate_visualization)
            graph.add_node("store_history", self.store_history)

            graph.add_edge(START, "execute_sql")
            graph.add_conditional_edges(
                "execute_sql",
                self._route_after_execute,
                {
                    "self_correct_sql": "self_correct_sql",
                    "generate_visualization": "generate_visualization",
                },
            )
            graph.add_conditional_edges(
                "self_correct_sql",
                self._route_after_correction,
                {
                    "generate_visualization": "generate_visualization",
                    "store_history": "store_history",
                },
            )
            graph.add_edge("generate_visualization", "store_history")
            graph.add_edge("store_history", END)
            return graph.compile()
        except Exception:
            return None

    def _route_after_execute(self, state: AgentState) -> str:
        if state.get("status") == "execution_failed":
            return "self_correct_sql"
        return "generate_visualization"

    def _route_after_correction(self, state: AgentState) -> str:
        if state.get("status") == "completed":
            return "generate_visualization"
        return "store_history"

    def run_to_review(self, question: str, session_id: Optional[str], provider: Optional[str] = None) -> AgentState:
        if not session_id:
            with get_db_session() as db:
                session_id = uuid.uuid4().hex
                db.execute(
                    app_sessions.insert().values(
                        id=session_id,
                        created_at=datetime.now(timezone.utc),
                        memory_json=to_json({"turns": [], "last_sql": None, "last_question": None}),
                    )
                )
        state: AgentState = {"question": question, "session_id": session_id, "provider": provider}
        if self.review_graph:
            return self.review_graph.invoke(state)
        for node in [
            self.understand_question,
            self.retrieve_schema_context,
            self.retrieve_historical_queries,
            self.generate_sql,
            self.validate_sql,
            self.human_review,
            self.store_history,
        ]:
            state.update(node(state))
        return state

    def understand_question(self, state: AgentState) -> AgentState:
        with get_db_session() as db:
            memory = get_session_memory(db, state["session_id"])
        question = state["question"].strip()
        resolved = question
        if memory.get("last_question") and any(
            phrase in question.lower() for phrase in ["now ", "group it", "show only", "plot this", "last month"]
        ):
            resolved = f"{question}\nFollow-up to: {memory.get('last_question')}\nPrevious SQL: {memory.get('last_sql')}"
        return {"memory": memory, "resolved_question": resolved}

    def retrieve_schema_context(self, state: AgentState) -> AgentState:
        context = retrieve_schema_context(state["resolved_question"], self.engine)
        return {"schema_context": context}

    def retrieve_historical_queries(self, state: AgentState) -> AgentState:
        with get_db_session() as db:
            context = retrieve_historical_queries(state["resolved_question"], state["session_id"], db)
        return {"historical_context": context}

    def generate_sql(self, state: AgentState) -> AgentState:
        start = time.perf_counter()
        try:
            result = llm_generate_sql(
                state["resolved_question"],
                state["schema_context"],
                state["historical_context"],
                state.get("memory", {}),
                self.settings,
                state.get("provider"),
            )
            return {
                "generated_sql": result.get("sql"),
                "chart_hint": result.get("chart"),
                "status": "generated",
                "error": result.get("error"),
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        except Exception as exc:
            return {
                "generated_sql": None,
                "status": "generation_failed",
                "error": str(exc),
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            }

    def validate_sql(self, state: AgentState) -> AgentState:
        sql = state.get("generated_sql")
        if not sql:
            return {"status": "generation_failed", "error": state.get("error") or "No SQL was generated."}
        validation = validate_select_sql(sql, self.settings.query_row_limit)
        if not validation.ok:
            return {"status": "validation_failed", "error": validation.reason}
        return {"generated_sql": validation.sql, "status": "pending_review"}

    def human_review(self, state: AgentState) -> AgentState:
        return {"requires_review": True, "status": state.get("status", "pending_review")}

    def store_history(self, state: AgentState) -> AgentState:
        query_id = state.get("query_id") or uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        with get_db_session() as db:
            existing = db.execute(select(query_runs.c.id).where(query_runs.c.id == query_id)).first()
            values = {
                "session_id": state["session_id"],
                "question": state["question"],
                "resolved_question": state.get("resolved_question"),
                "generated_sql": state.get("generated_sql"),
                "corrected_sql": state.get("corrected_sql"),
                "final_sql": state.get("final_sql"),
                "status": state.get("status", "pending_review"),
                "schema_context": state.get("schema_context"),
                "historical_context": state.get("historical_context"),
                "result_json": to_json({"columns": state.get("columns", []), "rows": state.get("rows", [])})
                if "rows" in state
                else None,
                "chart_json": to_json(state.get("plotly_json")) if state.get("plotly_json") else None,
                "chart_png_base64": state.get("chart_png_base64"),
                "error": state.get("error"),
                "latency_ms": state.get("latency_ms"),
                "updated_at": now,
            }
            if existing:
                db.execute(query_runs.update().where(query_runs.c.id == query_id).values(**values))
            else:
                values["id"] = query_id
                values["created_at"] = now
                db.execute(query_runs.insert().values(**values))
        return {"query_id": query_id}

    def approve_query(self, query_id: str, edited_sql: Optional[str] = None, feedback: Optional[str] = None) -> AgentState:
        with get_db_session() as db:
            row = db.execute(select(query_runs).where(query_runs.c.id == query_id)).mappings().first()
            if not row:
                raise ValueError("Query not found.")
            memory = get_session_memory(db, row["session_id"])
        sql = edited_sql or row["generated_sql"]
        state: AgentState = {
            "query_id": query_id,
            "session_id": row["session_id"],
            "question": row["question"],
            "resolved_question": row["resolved_question"] or row["question"],
            "provider": None,
            "schema_context": row["schema_context"] or retrieve_schema_context(row["question"], self.engine),
            "historical_context": row["historical_context"] or "",
            "memory": memory,
            "generated_sql": row["generated_sql"],
            "corrected_sql": edited_sql if edited_sql else None,
            "final_sql": sql,
            "chart_hint": None,
        }
        state.update(self.validate_final_sql(state))
        if state["status"] == "validation_failed":
            state.update(self.store_execution_result(state, feedback))
            return state

        if self.execution_graph:
            state = self.execution_graph.invoke(state)
        else:
            state.update(self.execute_sql(state))
            if state["status"] == "execution_failed":
                state.update(self.self_correct_sql(state))
            if state["status"] == "completed":
                state.update(self.generate_visualization(state))
        state.update(self.store_execution_result(state, feedback))
        return state

    def validate_final_sql(self, state: AgentState) -> AgentState:
        validation = validate_select_sql(state.get("final_sql") or "", self.settings.query_row_limit)
        if not validation.ok:
            return {"status": "validation_failed", "error": validation.reason}
        return {"final_sql": validation.sql, "status": "approved"}

    def execute_sql(self, state: AgentState) -> AgentState:
        start = time.perf_counter()
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(state["final_sql"]))
                rows = rows_to_dicts(result.fetchall())
                columns = list(result.keys())
            return {
                "status": "completed",
                "rows": rows,
                "columns": columns,
                "error": None,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        except Exception as exc:
            return {
                "status": "execution_failed",
                "error": str(exc),
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            }

    def self_correct_sql(self, state: AgentState) -> AgentState:
        failed_sql = state.get("final_sql") or state.get("generated_sql") or ""
        repaired = deterministic_sql_repair(failed_sql, state.get("error") or "")
        if not repaired:
            repaired = llm_correct_sql(
                state["resolved_question"],
                failed_sql,
                state.get("error") or "",
                state.get("schema_context") or "",
                state.get("historical_context") or "",
                state.get("memory", {}),
                self.settings,
                state.get("provider"),
            )
        if not repaired:
            return state
        validation = validate_select_sql(repaired, self.settings.query_row_limit)
        if not validation.ok:
            return {"status": "execution_failed", "corrected_sql": repaired, "error": validation.reason}
        retry_state = {**state, "final_sql": validation.sql, "corrected_sql": validation.sql}
        executed = self.execute_sql(retry_state)
        return {**executed, "corrected_sql": validation.sql, "final_sql": validation.sql}

    def generate_visualization(self, state: AgentState) -> AgentState:
        rows = state.get("rows", [])
        plotly_json = generate_plotly_json(rows, state["question"], state.get("chart_hint"))
        png = generate_matplotlib_png(rows, state.get("chart_hint"))
        return {"plotly_json": plotly_json, "chart_png_base64": png}

    def store_execution_result(self, state: AgentState, feedback: Optional[str]) -> AgentState:
        now = datetime.now(timezone.utc)
        with get_db_session() as db:
            values = {
                "corrected_sql": state.get("corrected_sql"),
                "final_sql": state.get("final_sql"),
                "status": state.get("status"),
                "result_json": to_json({"columns": state.get("columns", []), "rows": state.get("rows", [])}),
                "chart_json": to_json(state.get("plotly_json")) if state.get("plotly_json") else None,
                "chart_png_base64": state.get("chart_png_base64"),
                "feedback": feedback,
                "error": state.get("error"),
                "latency_ms": state.get("latency_ms"),
                "updated_at": now,
            }
            db.execute(query_runs.update().where(query_runs.c.id == state["query_id"]).values(**values))
            update_session_memory(db, state["session_id"], state["question"], state.get("final_sql"), state["status"])
        return state

    def reject_query(self, query_id: str, feedback: Optional[str]) -> None:
        with get_db_session() as db:
            row = db.execute(select(query_runs).where(query_runs.c.id == query_id)).mappings().first()
            if not row:
                raise ValueError("Query not found.")
            db.execute(
                query_runs.update()
                .where(query_runs.c.id == query_id)
                .values(status="rejected", feedback=feedback, updated_at=datetime.now(timezone.utc))
            )
            update_session_memory(db, row["session_id"], row["question"], row["generated_sql"], "rejected")

    def get_execution_payload(self, state: AgentState) -> Dict[str, Any]:
        return {
            "query_id": state["query_id"],
            "session_id": state["session_id"],
            "question": state["question"],
            "generated_sql": state.get("generated_sql"),
            "corrected_sql": state.get("corrected_sql"),
            "final_sql": state.get("final_sql"),
            "status": state.get("status", "unknown"),
            "columns": state.get("columns", []),
            "rows": state.get("rows", []),
            "plotly_json": state.get("plotly_json"),
            "chart_png_available": bool(state.get("chart_png_base64")),
            "error": state.get("error"),
            "latency_ms": state.get("latency_ms"),
        }


agent = TextToSQLAgent()

