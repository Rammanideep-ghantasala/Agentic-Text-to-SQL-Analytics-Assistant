from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SessionResponse(BaseModel):
    session_id: str
    demo_mode: bool


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=2)
    session_id: Optional[str] = None
    provider: Optional[str] = Field(default=None, description="openai, ollama, or demo")


class QueryDraftResponse(BaseModel):
    query_id: str
    session_id: str
    question: str
    resolved_question: Optional[str] = None
    generated_sql: Optional[str] = None
    status: str
    requires_review: bool = True
    schema_context: Optional[str] = None
    historical_context: Optional[str] = None
    error: Optional[str] = None
    demo_mode: bool


class ReviewEditRequest(BaseModel):
    sql: str = Field(..., min_length=3)
    feedback: Optional[str] = None


class ReviewRejectRequest(BaseModel):
    feedback: Optional[str] = None


class QueryExecutionResponse(BaseModel):
    query_id: str
    session_id: str
    question: str
    generated_sql: Optional[str]
    corrected_sql: Optional[str] = None
    final_sql: Optional[str] = None
    status: str
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    plotly_json: Optional[Dict[str, Any]] = None
    chart_png_available: bool = False
    error: Optional[str] = None
    latency_ms: Optional[float] = None


class HistoryItem(BaseModel):
    query_id: str
    question: str
    generated_sql: Optional[str]
    corrected_sql: Optional[str]
    final_sql: Optional[str]
    status: str
    created_at: str
    feedback: Optional[str] = None
    error: Optional[str] = None


class SchemaResponse(BaseModel):
    tables: List[Dict[str, Any]]


class BenchmarkRequest(BaseModel):
    providers: List[str] = Field(default_factory=lambda: ["openai", "ollama"])
    questions: Optional[List[str]] = None

