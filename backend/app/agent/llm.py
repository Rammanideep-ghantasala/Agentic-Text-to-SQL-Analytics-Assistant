import re
from typing import Any, Dict, Optional

import requests

from app.agent.demo_data import plan_demo_query
from app.config import Settings


SYSTEM_PROMPT = """You are a senior analytics engineer generating safe SQL for a business analytics database.
Return exactly one SELECT statement. Do not include markdown, comments, explanations, DDL, DML, or multiple statements.
Prefer explicit joins. Use only the schema provided. Keep results concise and aggregation-friendly."""


def build_user_prompt(
    question: str,
    schema_context: str,
    historical_context: str,
    memory: Dict[str, Any],
    failed_sql: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    prompt = f"""
Question:
{question}

Session memory:
Last question: {memory.get("last_question")}
Last SQL: {memory.get("last_sql")}

Relevant schema:
{schema_context}

Similar historical queries:
{historical_context}
"""
    if failed_sql and error:
        prompt += f"""
The previous SQL failed.
Failed SQL:
{failed_sql}

Database error:
{error}

Return a corrected SELECT statement only.
"""
    return prompt


def extract_sql(text: str) -> str:
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def generate_sql(
    question: str,
    schema_context: str,
    historical_context: str,
    memory: Dict[str, Any],
    settings: Settings,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    provider = (provider or "").lower()
    if provider == "demo" or settings.effective_demo_mode:
        plan = plan_demo_query(question, memory)
        return {
            "sql": plan["sql"],
            "provider": "demo",
            "chart": plan.get("chart", "bar"),
            "matched": plan.get("matched", True),
            "match_score": plan.get("match_score"),
            "error": plan.get("error"),
        }
    if provider == "ollama":
        return generate_with_ollama(question, schema_context, historical_context, memory, settings)
    return generate_with_openai(question, schema_context, historical_context, memory, settings)


def correct_sql(
    question: str,
    failed_sql: str,
    error: str,
    schema_context: str,
    historical_context: str,
    memory: Dict[str, Any],
    settings: Settings,
    provider: Optional[str] = None,
) -> Optional[str]:
    if settings.effective_demo_mode:
        return None
    try:
        provider = (provider or "").lower()
        if provider == "ollama":
            result = generate_with_ollama(question, schema_context, historical_context, memory, settings, failed_sql, error)
        else:
            result = generate_with_openai(question, schema_context, historical_context, memory, settings, failed_sql, error)
        return result.get("sql")
    except Exception:
        return None


def generate_with_openai(
    question: str,
    schema_context: str,
    historical_context: str,
    memory: Dict[str, Any],
    settings: Settings,
    failed_sql: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_prompt(question, schema_context, historical_context, memory, failed_sql, error),
            },
        ],
    )
    content = response.choices[0].message.content or ""
    return {"sql": extract_sql(content), "provider": "openai", "chart": "auto"}


def generate_with_ollama(
    question: str,
    schema_context: str,
    historical_context: str,
    memory: Dict[str, Any],
    settings: Settings,
    failed_sql: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    if not settings.ollama_base_url:
        raise RuntimeError("OLLAMA_BASE_URL is not configured.")
    prompt = SYSTEM_PROMPT + "\n\n" + build_user_prompt(question, schema_context, historical_context, memory, failed_sql, error)
    response = requests.post(
        f"{settings.ollama_base_url.rstrip('/')}/api/generate",
        json={"model": settings.ollama_model, "prompt": prompt, "stream": False, "options": {"temperature": 0}},
        timeout=120,
    )
    response.raise_for_status()
    content = response.json().get("response", "")
    return {"sql": extract_sql(content), "provider": "ollama", "chart": "auto"}

