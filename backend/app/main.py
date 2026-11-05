import base64
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select

from app.agent.demo_data import DEMO_QUESTIONS
from app.agent.graph import agent
from app.benchmark import run_benchmark
from app.config import get_settings
from app.database import (
    ENGINE,
    create_session_record,
    from_json,
    get_db_session,
    init_database,
    introspect_schema,
    query_runs,
)
from app.models import (
    BenchmarkRequest,
    HistoryItem,
    QueryDraftResponse,
    QueryExecutionResponse,
    QueryRequest,
    ReviewEditRequest,
    ReviewRejectRequest,
    SchemaResponse,
    SessionResponse,
)
from app.rate_limit import protect_expensive_call


settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_database()


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "demo_mode": settings.effective_demo_mode,
        "llm_providers": {
            "openai": bool(settings.openai_api_key),
            "ollama": bool(settings.ollama_base_url),
        },
    }


@app.post("/sessions", response_model=SessionResponse)
def create_session() -> SessionResponse:
    init_database()
    return SessionResponse(session_id=create_session_record(), demo_mode=settings.effective_demo_mode)


@app.post("/query", response_model=QueryDraftResponse)
def create_query(payload: QueryRequest, request: Request, _: None = Depends(protect_expensive_call)) -> QueryDraftResponse:
    init_database()
    state = agent.run_to_review(payload.question, payload.session_id, payload.provider)
    return QueryDraftResponse(
        query_id=state["query_id"],
        session_id=state["session_id"],
        question=state["question"],
        resolved_question=state.get("resolved_question"),
        generated_sql=state.get("generated_sql"),
        status=state.get("status", "pending_review"),
        requires_review=True,
        schema_context=state.get("schema_context"),
        historical_context=state.get("historical_context"),
        error=state.get("error"),
        demo_mode=settings.effective_demo_mode,
    )


@app.post("/review/{query_id}/approve", response_model=QueryExecutionResponse)
def approve_query(query_id: str) -> QueryExecutionResponse:
    try:
        state = agent.approve_query(query_id)
        return QueryExecutionResponse(**agent.get_execution_payload(state))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Approval failed: {exc}") from exc


@app.post("/review/{query_id}/edit", response_model=QueryExecutionResponse)
def edit_query(query_id: str, payload: ReviewEditRequest) -> QueryExecutionResponse:
    try:
        state = agent.approve_query(query_id, edited_sql=payload.sql, feedback=payload.feedback)
        return QueryExecutionResponse(**agent.get_execution_payload(state))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Edited SQL execution failed: {exc}") from exc


@app.post("/review/{query_id}/reject")
def reject_query(query_id: str, payload: ReviewRejectRequest) -> Dict[str, str]:
    try:
        agent.reject_query(query_id, payload.feedback)
        return {"status": "rejected", "query_id": query_id}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/history/{session_id}", response_model=List[HistoryItem])
def history(session_id: str) -> List[HistoryItem]:
    with get_db_session() as db:
        rows = db.execute(
            select(query_runs)
            .where(query_runs.c.session_id == session_id)
            .order_by(desc(query_runs.c.created_at))
            .limit(50)
        ).mappings()
        return [
            HistoryItem(
                query_id=row["id"],
                question=row["question"],
                generated_sql=row["generated_sql"],
                corrected_sql=row["corrected_sql"],
                final_sql=row["final_sql"],
                status=row["status"],
                created_at=row["created_at"].isoformat(),
                feedback=row["feedback"],
                error=row["error"],
            )
            for row in rows
        ]


@app.get("/schema", response_model=SchemaResponse)
def schema() -> SchemaResponse:
    init_database()
    return SchemaResponse(tables=introspect_schema(ENGINE))


@app.get("/chart/{query_id}")
def chart(query_id: str, format: str = Query(default="json", pattern="^(json|png)$")) -> Any:
    with get_db_session() as db:
        row = db.execute(select(query_runs).where(query_runs.c.id == query_id)).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Query not found.")
        if format == "png":
            if not row["chart_png_base64"]:
                raise HTTPException(status_code=404, detail="PNG chart export is not available for this query.")
            return Response(content=base64.b64decode(row["chart_png_base64"]), media_type="image/png")
        return from_json(row["chart_json"], {"data": [], "layout": {"title": "No chart available"}})


@app.post("/benchmark")
def benchmark(payload: BenchmarkRequest, request: Request, _: None = Depends(protect_expensive_call)) -> Dict[str, Any]:
    return run_benchmark(payload.providers, payload.questions)


@app.get("/demo/questions")
def demo_questions() -> Dict[str, List[str]]:
    return {"questions": DEMO_QUESTIONS}

