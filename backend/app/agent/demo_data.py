from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional


DEMO_SQL: Dict[str, Dict[str, str]] = {
    "monthly_revenue": {
        "question": "What is total revenue by month in 2026?",
        "chart": "line",
        "sql": """
SELECT
  substr(CAST(o.order_date AS TEXT), 1, 7) AS month,
  ROUND(SUM(p.amount), 2) AS revenue
FROM orders o
JOIN payments p ON p.order_id = o.id
WHERE p.status = 'paid'
GROUP BY substr(CAST(o.order_date AS TEXT), 1, 7)
ORDER BY month
""",
    },
    "top_products": {
        "question": "Which products generated the most revenue?",
        "chart": "bar",
        "sql": """
SELECT
  pr.name AS product,
  pr.category,
  ROUND(SUM(p.amount), 2) AS revenue
FROM orders o
JOIN products pr ON pr.id = o.product_id
JOIN payments p ON p.order_id = o.id
WHERE p.status = 'paid'
GROUP BY pr.name, pr.category
ORDER BY revenue DESC
LIMIT 5
""",
    },
    "revenue_by_region": {
        "question": "Show revenue by region.",
        "chart": "bar",
        "sql": """
SELECT
  r.name AS region,
  ROUND(SUM(p.amount), 2) AS revenue
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN regions r ON r.id = c.region_id
JOIN payments p ON p.order_id = o.id
WHERE p.status = 'paid'
GROUP BY r.name
ORDER BY revenue DESC
""",
    },
    "segment_aov": {
        "question": "What is average order value by customer segment?",
        "chart": "bar",
        "sql": """
SELECT
  c.segment,
  ROUND(AVG(o.total_amount), 2) AS average_order_value,
  COUNT(o.id) AS orders
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status <> 'cancelled'
GROUP BY c.segment
ORDER BY average_order_value DESC
""",
    },
    "unpaid_orders": {
        "question": "Which customers have pending or failed payments?",
        "chart": "table",
        "sql": """
SELECT
  c.name AS customer,
  c.segment,
  r.name AS region,
  COUNT(o.id) AS open_orders,
  ROUND(SUM(p.amount), 2) AS outstanding_amount
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN regions r ON r.id = c.region_id
JOIN payments p ON p.order_id = o.id
WHERE p.status IN ('pending', 'failed')
GROUP BY c.name, c.segment, r.name
ORDER BY outstanding_amount DESC
""",
    },
    "category_margin": {
        "question": "Which product categories produce the highest gross margin?",
        "chart": "bar",
        "sql": """
SELECT
  pr.category,
  ROUND(SUM(p.amount * pr.margin_percent / 100.0), 2) AS estimated_gross_margin,
  ROUND(SUM(p.amount), 2) AS revenue
FROM orders o
JOIN products pr ON pr.id = o.product_id
JOIN payments p ON p.order_id = o.id
WHERE p.status = 'paid'
GROUP BY pr.category
ORDER BY estimated_gross_margin DESC
""",
    },
    "payment_methods": {
        "question": "Break down revenue by payment method.",
        "chart": "pie",
        "sql": """
SELECT
  p.method,
  ROUND(SUM(p.amount), 2) AS revenue,
  COUNT(*) AS payments
FROM payments p
WHERE p.status = 'paid'
GROUP BY p.method
ORDER BY revenue DESC
""",
    },
    "last_month_region": {
        "question": "Show last month revenue by region.",
        "chart": "bar",
        "sql": """
SELECT
  r.name AS region,
  ROUND(SUM(p.amount), 2) AS revenue
FROM orders o
JOIN customers c ON c.id = o.customer_id
JOIN regions r ON r.id = c.region_id
JOIN payments p ON p.order_id = o.id
WHERE p.status = 'paid'
  AND o.order_date >= '2026-10-01'
  AND o.order_date < '2026-11-01'
GROUP BY r.name
ORDER BY revenue DESC
""",
    },
    "repeat_customers": {
        "question": "Who are our repeat customers by total spend?",
        "chart": "bar",
        "sql": """
SELECT
  c.name AS customer,
  COUNT(o.id) AS orders,
  ROUND(SUM(p.amount), 2) AS total_spend
FROM customers c
JOIN orders o ON o.customer_id = c.id
JOIN payments p ON p.order_id = o.id
WHERE p.status = 'paid'
GROUP BY c.name
HAVING COUNT(o.id) > 1
ORDER BY total_spend DESC
LIMIT 10
""",
    },
    "sales_managers": {
        "question": "Which sales managers own the most revenue?",
        "chart": "bar",
        "sql": """
SELECT
  r.sales_manager,
  r.name AS region,
  ROUND(SUM(p.amount), 2) AS revenue
FROM regions r
JOIN customers c ON c.region_id = r.id
JOIN orders o ON o.customer_id = c.id
JOIN payments p ON p.order_id = o.id
WHERE p.status = 'paid'
GROUP BY r.sales_manager, r.name
ORDER BY revenue DESC
""",
    },
}


DEMO_QUESTIONS = [item["question"] for item in DEMO_SQL.values()]


FOLLOW_UP_HINTS = [
    (("group", "region"), "revenue_by_region"),
    (("last month",), "last_month_region"),
    (("bar chart",), "top_products"),
    (("payment", "method"), "payment_methods"),
    (("repeat", "customer"), "repeat_customers"),
]


def normalize_question(question: str) -> str:
    return " ".join(question.lower().strip().split())


def plan_demo_query(question: str, memory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    normalized = normalize_question(question)
    for hints, key in FOLLOW_UP_HINTS:
        if all(hint in normalized for hint in hints):
            item = DEMO_SQL[key]
            return {**item, "key": key, "matched": True, "match_score": 1.0}

    best_key = None
    best_score = 0.0
    for key, item in DEMO_SQL.items():
        score = SequenceMatcher(None, normalized, normalize_question(item["question"])).ratio()
        tokens = set(normalized.split())
        reference_tokens = set(normalize_question(item["question"]).split())
        overlap = len(tokens & reference_tokens) / max(len(tokens | reference_tokens), 1)
        score = max(score, overlap)
        if score > best_score:
            best_key = key
            best_score = score

    if best_key and best_score >= 0.22:
        item = DEMO_SQL[best_key]
        return {**item, "key": best_key, "matched": True, "match_score": round(best_score, 3)}

    item = DEMO_SQL["monthly_revenue"]
    return {
        **item,
        "key": "monthly_revenue",
        "matched": False,
        "match_score": round(best_score, 3),
        "error": "Demo mode supports the predefined business questions shown in the UI.",
    }

