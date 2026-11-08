from app.agent.sql import deterministic_sql_repair, validate_select_sql


def test_allows_safe_select_with_limit() -> None:
    result = validate_select_sql("SELECT name, total_amount FROM orders ORDER BY total_amount DESC", row_limit=50)
    assert result.ok
    assert result.sql is not None
    assert "LIMIT 50" in result.sql


def test_rejects_delete() -> None:
    result = validate_select_sql("DELETE FROM customers")
    assert not result.ok
    assert "Unsafe" in (result.reason or "") or "Only SELECT" in (result.reason or "")


def test_rejects_multiple_statements() -> None:
    result = validate_select_sql("SELECT * FROM orders; DROP TABLE orders")
    assert not result.ok
    assert "one SQL statement" in (result.reason or "")


def test_rejects_comments() -> None:
    result = validate_select_sql("SELECT * FROM orders -- hide an update")
    assert not result.ok


def test_repairs_postgres_month_functions_for_sqlite_fallback() -> None:
    repaired = deterministic_sql_repair(
        """
        SELECT DATE_TRUNC('month', o.order_date) AS month, SUM(o.total_amount) AS revenue
        FROM orders o
        WHERE EXTRACT(YEAR FROM o.order_date) = 2026
        GROUP BY month
        """,
        "sqlite3.OperationalError near FROM syntax error",
    )
    assert repaired is not None
    assert "substr(CAST(o.order_date AS TEXT), 1, 7)" in repaired
    assert "substr(CAST(o.order_date AS TEXT), 1, 4) = '2026'" in repaired

