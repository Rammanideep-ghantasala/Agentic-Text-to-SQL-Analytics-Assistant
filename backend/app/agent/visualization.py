import base64
import io
from typing import Any, Dict, List, Optional


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def infer_chart_type(rows: List[Dict[str, Any]], hint: Optional[str] = None) -> str:
    if hint and hint != "auto":
        return hint
    if not rows:
        return "table"
    columns = list(rows[0].keys())
    numeric = [col for col in columns if any(_is_number(row.get(col)) for row in rows)]
    if len(columns) >= 2 and "month" in columns[0].lower():
        return "line"
    if len(numeric) >= 1 and len(rows) <= 8:
        return "bar"
    return "table"


def generate_plotly_json(rows: List[Dict[str, Any]], question: str, hint: Optional[str] = None) -> Dict[str, Any]:
    chart_type = infer_chart_type(rows, hint)
    if not rows or chart_type == "table":
        return {
            "data": [],
            "layout": {
                "title": "Table result",
                "annotations": [{"text": "No chart generated for this result shape.", "showarrow": False}],
            },
            "chart_type": "table",
        }

    try:
        import plotly.graph_objects as go

        columns = list(rows[0].keys())
        numeric_columns = [col for col in columns if any(_is_number(row.get(col)) for row in rows)]
        x_col = next((col for col in columns if col not in numeric_columns), columns[0])
        y_col = numeric_columns[0] if numeric_columns else columns[-1]
        x = [row.get(x_col) for row in rows]
        y = [row.get(y_col) for row in rows]

        if chart_type == "line":
            fig = go.Figure(data=[go.Scatter(x=x, y=y, mode="lines+markers", name=y_col)])
        elif chart_type == "pie":
            fig = go.Figure(data=[go.Pie(labels=x, values=y, hole=0.35)])
        else:
            fig = go.Figure(data=[go.Bar(x=x, y=y, marker_color="#2563eb", name=y_col)])
        fig.update_layout(
            title=question,
            template="plotly_white",
            margin={"l": 32, "r": 24, "t": 56, "b": 48},
            xaxis_title=x_col if chart_type != "pie" else None,
            yaxis_title=y_col if chart_type != "pie" else None,
        )
        payload = fig.to_plotly_json()
        payload["chart_type"] = chart_type
        return payload
    except Exception as exc:
        return {
            "data": [],
            "layout": {"title": "Chart unavailable", "annotations": [{"text": str(exc), "showarrow": False}]},
            "chart_type": "table",
        }


def generate_matplotlib_png(rows: List[Dict[str, Any]], hint: Optional[str] = None) -> Optional[str]:
    if not rows:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        chart_type = infer_chart_type(rows, hint)
        if chart_type == "table":
            return None
        columns = list(rows[0].keys())
        numeric_columns = [col for col in columns if any(_is_number(row.get(col)) for row in rows)]
        x_col = next((col for col in columns if col not in numeric_columns), columns[0])
        y_col = numeric_columns[0] if numeric_columns else columns[-1]
        x = [str(row.get(x_col)) for row in rows]
        y = [float(row.get(y_col) or 0) for row in rows]

        fig, ax = plt.subplots(figsize=(9, 4.8))
        if chart_type == "line":
            ax.plot(x, y, marker="o", color="#2563eb")
        elif chart_type == "pie":
            ax.pie(y, labels=x, autopct="%1.1f%%")
        else:
            ax.bar(x, y, color="#2563eb")
        if chart_type != "pie":
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.tick_params(axis="x", rotation=30)
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=150)
        plt.close(fig)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return None

