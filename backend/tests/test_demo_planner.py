from app.agent.demo_data import DEMO_QUESTIONS, plan_demo_query


def test_demo_has_recruiter_friendly_question_set() -> None:
    assert 8 <= len(DEMO_QUESTIONS) <= 10


def test_demo_planner_maps_region_followup() -> None:
    plan = plan_demo_query("Now group it by region", {"last_question": "Show total revenue", "last_sql": "SELECT 1"})
    assert plan["matched"]
    assert "regions" in plan["sql"]
    assert plan["chart"] == "bar"


def test_demo_planner_returns_select_sql() -> None:
    plan = plan_demo_query("Which products generated the most revenue?")
    assert plan["sql"].strip().lower().startswith("select")

