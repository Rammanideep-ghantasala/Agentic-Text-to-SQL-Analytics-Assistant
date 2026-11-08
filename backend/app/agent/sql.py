import re
from dataclasses import dataclass
from typing import Optional


DANGEROUS_KEYWORDS = {
    "alter",
    "attach",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "grant",
    "insert",
    "merge",
    "replace",
    "revoke",
    "truncate",
    "update",
    "vacuum",
}


@dataclass
class SqlValidationResult:
    ok: bool
    sql: Optional[str] = None
    reason: Optional[str] = None


def clean_sql(sql: str) -> str:
    sql = sql.strip()
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", sql, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        sql = fenced.group(1).strip()
    return sql.rstrip(";").strip()


def validate_select_sql(sql: str, row_limit: int = 500) -> SqlValidationResult:
    cleaned = clean_sql(sql)
    if not cleaned:
        return SqlValidationResult(False, reason="SQL is empty.")
    if ";" in cleaned:
        return SqlValidationResult(False, reason="Only one SQL statement is allowed.")
    if re.search(r"(--|/\*)", cleaned):
        return SqlValidationResult(False, reason="SQL comments are not allowed in executable queries.")

    tokens = {token.lower() for token in re.findall(r"[A-Za-z_]+", cleaned)}
    blocked = sorted(tokens & DANGEROUS_KEYWORDS)
    if blocked:
        return SqlValidationResult(False, reason=f"Unsafe SQL keyword detected: {', '.join(blocked)}.")

    try:
        import sqlglot
        from sqlglot import exp

        parsed = sqlglot.parse(cleaned)
        if len(parsed) != 1:
            return SqlValidationResult(False, reason="Only one SQL statement is allowed.")
        tree = parsed[0]
        if not isinstance(tree, (exp.Select, exp.Union)):
            return SqlValidationResult(False, reason="Only SELECT queries are allowed.")
        dangerous_nodes = tuple(
            getattr(exp, name)
            for name in ["Delete", "Drop", "Insert", "Update", "Create", "Alter", "Command"]
            if hasattr(exp, name)
        )
        if dangerous_nodes and any(tree.find(node_type) for node_type in dangerous_nodes):
            return SqlValidationResult(False, reason="Query contains a write or DDL operation.")
    except ImportError:
        if not re.match(r"^\s*(with|select)\b", cleaned, flags=re.IGNORECASE):
            return SqlValidationResult(False, reason="Only SELECT queries are allowed.")
    except Exception as exc:
        return SqlValidationResult(False, reason=f"SQL parse error: {exc}")

    limited = apply_limit(cleaned, row_limit)
    return SqlValidationResult(True, sql=limited)


def apply_limit(sql: str, row_limit: int) -> str:
    if re.search(r"\blimit\s+\d+\b", sql, flags=re.IGNORECASE):
        return sql
    return f"{sql} LIMIT {row_limit}"


def deterministic_sql_repair(sql: str, error: str) -> Optional[str]:
    lowered = error.lower()
    repaired = clean_sql(sql)
    portable = re.sub(
        r"DATE_TRUNC\(\s*'month'\s*,\s*([^)]+?)\s*\)",
        r"substr(CAST(\1 AS TEXT), 1, 7)",
        repaired,
        flags=re.IGNORECASE,
    )
    portable = re.sub(
        r"EXTRACT\(\s*YEAR\s+FROM\s+([^)]+?)\s*\)\s*=\s*(\d{4})",
        r"substr(CAST(\1 AS TEXT), 1, 4) = '\2'",
        portable,
        flags=re.IGNORECASE,
    )
    if portable != repaired and any(term in lowered for term in ["syntax", "date_trunc", "extract"]):
        return portable
    replacements = {
        "revenue": "total_amount",
        "customer_name": "name",
        "region": "name",
        "order_month": "month",
    }
    if "no such column" in lowered or "does not exist" in lowered:
        for bad, good in replacements.items():
            if re.search(rf"\b{bad}\b", repaired, flags=re.IGNORECASE):
                return re.sub(rf"\b{bad}\b", good, repaired, flags=re.IGNORECASE)
    if "syntax" in lowered:
        return clean_sql(repaired)
    return None

