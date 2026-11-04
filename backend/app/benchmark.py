import time
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.agent.demo_data import DEMO_SQL
from app.agent.llm import generate_sql
from app.agent.rag import retrieve_schema_context
from app.agent.sql import validate_select_sql
from app.config import get_settings
from app.database import ENGINE


BENCHMARK_CASES = [
    {
        "question": item["question"],
        "must_include": ["select"],
    }
    for item in DEMO_SQL.values()
]


def provider_available(provider: str) -> tuple[bool, str]:
    settings = get_settings()
    if provider == "openai" and not settings.openai_api_key:
        return False, "OPENAI_API_KEY is not configured."
    if provider == "ollama" and not settings.ollama_base_url:
        return False, "OLLAMA_BASE_URL is not configured."
    if provider not in {"openai", "ollama", "demo"}:
        return False, f"Unknown provider: {provider}"
    return True, "available"


def run_benchmark(providers: List[str], questions: Optional[List[str]] = None) -> Dict[str, Any]:
    settings = get_settings()
    cases = BENCHMARK_CASES
    if questions:
        cases = [{"question": question, "must_include": ["select"]} for question in questions]

    schema_context = retrieve_schema_context("business analytics revenue customer orders products payments", ENGINE)
    results: List[Dict[str, Any]] = []
    for provider in providers:
        available, reason = provider_available(provider)
        provider_rows: List[Dict[str, Any]] = []
        if not available:
            results.append(
                {
                    "provider": provider,
                    "status": "skipped",
                    "reason": reason,
                    "summary": {
                        "total": len(cases),
                        "execution_success_rate": 0,
                        "sql_correctness_rate": 0,
                        "error_rate": 0,
                        "avg_latency_ms": None,
                    },
                    "cases": [],
                }
            )
            continue

        for case in cases:
            started = time.perf_counter()
            row: Dict[str, Any] = {"question": case["question"]}
            try:
                generated = generate_sql(
                    case["question"],
                    schema_context,
                    "Benchmark run; no history.",
                    {"turns": [], "last_sql": None, "last_question": None},
                    settings,
                    provider=provider,
                )
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                sql = generated.get("sql", "")
                validation = validate_select_sql(sql, settings.query_row_limit)
                execution_success = False
                execution_error = validation.reason
                if validation.ok and validation.sql:
                    try:
                        with ENGINE.connect() as connection:
                            connection.execute(text(validation.sql)).fetchmany(1)
                        execution_success = True
                        execution_error = None
                    except Exception as exc:
                        execution_error = str(exc)
                row.update(
                    {
                        "status": "completed" if execution_success else "execution_failed",
                        "sql": validation.sql or sql,
                        "latency_ms": latency_ms,
                        "sql_correct": validation.ok and all(token in sql.lower() for token in case["must_include"]),
                        "execution_success": execution_success,
                        "error": execution_error,
                    }
                )
            except Exception as exc:
                row.update(
                    {
                        "status": "failed",
                        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                        "sql_correct": False,
                        "execution_success": False,
                        "error": str(exc),
                    }
                )
            provider_rows.append(row)

        total = len(provider_rows) or 1
        latencies = [row["latency_ms"] for row in provider_rows if row.get("latency_ms") is not None]
        results.append(
            {
                "provider": provider,
                "status": "completed",
                "summary": {
                    "total": len(provider_rows),
                    "execution_success_rate": round(sum(1 for row in provider_rows if row["execution_success"]) / total, 3),
                    "sql_correctness_rate": round(sum(1 for row in provider_rows if row["sql_correct"]) / total, 3),
                    "error_rate": round(sum(1 for row in provider_rows if row.get("error")) / total, 3),
                    "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
                },
                "cases": provider_rows,
            }
        )
    return {"results": results}

