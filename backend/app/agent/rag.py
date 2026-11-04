import re
from typing import Any, Dict, List

from sqlalchemy import desc, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.database import from_json, introspect_schema, query_runs


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text)}


def score_text(question: str, text: str) -> float:
    q_tokens = tokenize(question)
    text_tokens = tokenize(text)
    if not q_tokens or not text_tokens:
        return 0.0
    return len(q_tokens & text_tokens) / len(q_tokens | text_tokens)


def format_schema_doc(doc: Dict[str, Any]) -> str:
    columns = ", ".join(f"{col['name']}:{col['type']}" for col in doc["columns"])
    fks = "; ".join(f"{fk['column']} -> {fk['references']}" for fk in doc["foreign_keys"]) or "none"
    return f"Table {doc['table']} columns [{columns}] foreign_keys [{fks}]"


def retrieve_schema_context(question: str, engine: Engine, top_k: int = 5) -> str:
    docs = introspect_schema(engine)
    ranked = sorted(
        ((score_text(question, format_schema_doc(doc)), doc) for doc in docs),
        key=lambda item: item[0],
        reverse=True,
    )
    selected = [doc for score, doc in ranked[:top_k] if score > 0]
    if not selected:
        selected = docs[:top_k]
    return "\n".join(format_schema_doc(doc) for doc in selected)


def retrieve_historical_queries(question: str, session_id: str, db: Session, top_k: int = 3) -> str:
    rows = db.execute(
        select(
            query_runs.c.question,
            query_runs.c.final_sql,
            query_runs.c.generated_sql,
            query_runs.c.status,
            query_runs.c.result_json,
        )
        .where(query_runs.c.session_id == session_id)
        .order_by(desc(query_runs.c.created_at))
        .limit(20)
    ).all()
    candidates: List[tuple[float, str]] = []
    for row in rows:
        sql = row.final_sql or row.generated_sql
        if not sql:
            continue
        text = f"{row.question}\n{sql}"
        result = from_json(row.result_json, {})
        if result:
            text += f"\ncolumns: {', '.join(result.get('columns', []))}"
        candidates.append((score_text(question, text), f"Question: {row.question}\nSQL: {sql}\nStatus: {row.status}"))
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = [text for score, text in candidates[:top_k] if score > 0]
    return "\n\n".join(selected) if selected else "No similar historical queries found for this session."

