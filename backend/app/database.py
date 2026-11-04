import json
import random
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, Iterator, List, Optional

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


APP_METADATA = MetaData()
BUSINESS_METADATA = MetaData()


app_sessions = Table(
    "app_sessions",
    APP_METADATA,
    Column("id", String(64), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)),
    Column("memory_json", Text, nullable=False, default="{}"),
)


query_runs = Table(
    "query_runs",
    APP_METADATA,
    Column("id", String(64), primary_key=True),
    Column("session_id", String(64), ForeignKey("app_sessions.id"), nullable=False, index=True),
    Column("question", Text, nullable=False),
    Column("resolved_question", Text, nullable=True),
    Column("generated_sql", Text, nullable=True),
    Column("corrected_sql", Text, nullable=True),
    Column("final_sql", Text, nullable=True),
    Column("status", String(40), nullable=False, default="pending_review"),
    Column("schema_context", Text, nullable=True),
    Column("historical_context", Text, nullable=True),
    Column("result_json", Text, nullable=True),
    Column("chart_json", Text, nullable=True),
    Column("chart_png_base64", Text, nullable=True),
    Column("feedback", Text, nullable=True),
    Column("error", Text, nullable=True),
    Column("latency_ms", Float, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)),
)


regions = Table(
    "regions",
    BUSINESS_METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(80), nullable=False, unique=True),
    Column("country", String(80), nullable=False),
    Column("sales_manager", String(120), nullable=False),
)


customers = Table(
    "customers",
    BUSINESS_METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("email", String(160), nullable=False, unique=True),
    Column("segment", String(40), nullable=False),
    Column("region_id", Integer, ForeignKey("regions.id"), nullable=False),
    Column("signup_date", Date, nullable=False),
)


products = Table(
    "products",
    BUSINESS_METADATA,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("category", String(80), nullable=False),
    Column("unit_price", Numeric(12, 2), nullable=False),
    Column("margin_percent", Numeric(5, 2), nullable=False),
)


orders = Table(
    "orders",
    BUSINESS_METADATA,
    Column("id", Integer, primary_key=True),
    Column("customer_id", Integer, ForeignKey("customers.id"), nullable=False),
    Column("product_id", Integer, ForeignKey("products.id"), nullable=False),
    Column("order_date", Date, nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("total_amount", Numeric(12, 2), nullable=False),
    Column("status", String(40), nullable=False),
)


payments = Table(
    "payments",
    BUSINESS_METADATA,
    Column("id", Integer, primary_key=True),
    Column("order_id", Integer, ForeignKey("orders.id"), nullable=False),
    Column("payment_date", Date, nullable=True),
    Column("amount", Numeric(12, 2), nullable=False),
    Column("method", String(40), nullable=False),
    Column("status", String(40), nullable=False),
)


def normalize_database_url(url: Optional[str]) -> str:
    if not url:
        return "sqlite:///./text2sql_demo.db"
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def build_engine() -> Engine:
    settings = get_settings()
    url = normalize_database_url(settings.database_url)
    connect_args: Dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


ENGINE = build_engine()
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True)


@contextmanager
def get_db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def to_json(data: Any) -> str:
    def default(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return str(value)

    return json.dumps(data, default=default)


def from_json(raw: Optional[str], fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def create_session_record() -> str:
    session_id = uuid.uuid4().hex
    with get_db_session() as db:
        db.execute(
            app_sessions.insert().values(
                id=session_id,
                created_at=datetime.now(timezone.utc),
                memory_json=to_json({"turns": [], "last_sql": None, "last_question": None}),
            )
        )
    return session_id


def get_session_memory(db: Session, session_id: str) -> Dict[str, Any]:
    row = db.execute(select(app_sessions.c.memory_json).where(app_sessions.c.id == session_id)).first()
    if not row:
        return {"turns": [], "last_sql": None, "last_question": None}
    return from_json(row[0], {"turns": [], "last_sql": None, "last_question": None})


def update_session_memory(db: Session, session_id: str, question: str, sql: Optional[str], status: str) -> None:
    memory = get_session_memory(db, session_id)
    turns = memory.setdefault("turns", [])
    turns.append(
        {
            "question": question,
            "sql": sql,
            "status": status,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    memory["turns"] = turns[-8:]
    if status == "completed" and sql:
        memory["last_sql"] = sql
        memory["last_question"] = question
    db.execute(app_sessions.update().where(app_sessions.c.id == session_id).values(memory_json=to_json(memory)))


def init_database() -> None:
    APP_METADATA.create_all(ENGINE)
    BUSINESS_METADATA.create_all(ENGINE)
    with get_db_session() as db:
        region_count = db.execute(select(func.count()).select_from(regions)).scalar_one()
        if region_count == 0:
            seed_business_data(db)


def seed_business_data(db: Session) -> None:
    region_rows = [
        {"id": 1, "name": "North", "country": "United States", "sales_manager": "Avery Stone"},
        {"id": 2, "name": "South", "country": "United States", "sales_manager": "Jordan Blake"},
        {"id": 3, "name": "West", "country": "United States", "sales_manager": "Maya Chen"},
        {"id": 4, "name": "East", "country": "United States", "sales_manager": "Noah Patel"},
        {"id": 5, "name": "Central", "country": "United States", "sales_manager": "Riley Morgan"},
    ]
    customer_rows = [
        {"id": 1, "name": "Acme Retail", "email": "ops@acmeretail.example", "segment": "Enterprise", "region_id": 1, "signup_date": date(2024, 1, 15)},
        {"id": 2, "name": "Bluebird Foods", "email": "finance@bluebird.example", "segment": "SMB", "region_id": 2, "signup_date": date(2024, 3, 7)},
        {"id": 3, "name": "Canyon Outfitters", "email": "data@canyon.example", "segment": "Mid-Market", "region_id": 3, "signup_date": date(2024, 6, 21)},
        {"id": 4, "name": "Delta Health", "email": "analytics@deltahealth.example", "segment": "Enterprise", "region_id": 4, "signup_date": date(2024, 8, 5)},
        {"id": 5, "name": "Evergreen Supply", "email": "admin@evergreen.example", "segment": "SMB", "region_id": 5, "signup_date": date(2025, 1, 12)},
        {"id": 6, "name": "Futura Labs", "email": "ops@futuralabs.example", "segment": "Startup", "region_id": 3, "signup_date": date(2025, 2, 3)},
        {"id": 7, "name": "Granite Finance", "email": "reporting@granite.example", "segment": "Enterprise", "region_id": 1, "signup_date": date(2025, 4, 14)},
        {"id": 8, "name": "Harbor Logistics", "email": "bi@harbor.example", "segment": "Mid-Market", "region_id": 4, "signup_date": date(2025, 7, 30)},
        {"id": 9, "name": "Ion Commerce", "email": "growth@ion.example", "segment": "Startup", "region_id": 2, "signup_date": date(2025, 10, 1)},
        {"id": 10, "name": "Juniper Manufacturing", "email": "planning@juniper.example", "segment": "Mid-Market", "region_id": 5, "signup_date": date(2026, 1, 18)},
    ]
    product_rows = [
        {"id": 1, "name": "Insight Starter", "category": "Analytics", "unit_price": 99.0, "margin_percent": 61.0},
        {"id": 2, "name": "Insight Pro", "category": "Analytics", "unit_price": 249.0, "margin_percent": 68.0},
        {"id": 3, "name": "Workflow Automator", "category": "Automation", "unit_price": 399.0, "margin_percent": 57.0},
        {"id": 4, "name": "Compliance Vault", "category": "Security", "unit_price": 529.0, "margin_percent": 54.0},
        {"id": 5, "name": "Data Sync", "category": "Integration", "unit_price": 179.0, "margin_percent": 63.0},
        {"id": 6, "name": "AI Forecast Pack", "category": "AI", "unit_price": 699.0, "margin_percent": 72.0},
        {"id": 7, "name": "Support Desk Plus", "category": "Operations", "unit_price": 149.0, "margin_percent": 49.0},
        {"id": 8, "name": "Executive Dashboard", "category": "Analytics", "unit_price": 899.0, "margin_percent": 66.0},
    ]
    db.execute(regions.insert(), region_rows)
    db.execute(customers.insert(), customer_rows)
    db.execute(products.insert(), product_rows)

    random.seed(42)
    order_rows: List[Dict[str, Any]] = []
    payment_rows: List[Dict[str, Any]] = []
    start = date(2026, 1, 4)
    statuses = ["paid", "paid", "paid", "paid", "pending", "cancelled"]
    methods = ["card", "bank_transfer", "ach", "wire", "card"]

    product_lookup = {row["id"]: row for row in product_rows}
    for order_id in range(1, 73):
        product_id = random.randint(1, len(product_rows))
        customer_id = random.randint(1, len(customer_rows))
        quantity = random.randint(1, 9)
        order_date = start + timedelta(days=random.randint(0, 300))
        unit_price = product_lookup[product_id]["unit_price"]
        total_amount = round(quantity * unit_price * random.choice([0.9, 1.0, 1.0, 1.1]), 2)
        status = random.choice(statuses)
        order_rows.append(
            {
                "id": order_id,
                "customer_id": customer_id,
                "product_id": product_id,
                "order_date": order_date,
                "quantity": quantity,
                "total_amount": total_amount,
                "status": status,
            }
        )
        payment_status = "paid" if status == "paid" else ("failed" if status == "cancelled" else "pending")
        payment_date = order_date + timedelta(days=random.randint(0, 12)) if payment_status == "paid" else None
        payment_rows.append(
            {
                "id": order_id,
                "order_id": order_id,
                "payment_date": payment_date,
                "amount": total_amount,
                "method": random.choice(methods),
                "status": payment_status,
            }
        )

    db.execute(orders.insert(), order_rows)
    db.execute(payments.insert(), payment_rows)


def introspect_schema(engine: Engine) -> List[Dict[str, Any]]:
    inspector = inspect(engine)
    ignored = {"app_sessions", "query_runs"}
    docs: List[Dict[str, Any]] = []
    for table_name in sorted(name for name in inspector.get_table_names() if name not in ignored):
        columns = inspector.get_columns(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)
        docs.append(
            {
                "table": table_name,
                "columns": [
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                    }
                    for col in columns
                ],
                "foreign_keys": [
                    {
                        "column": ",".join(fk.get("constrained_columns", [])),
                        "references": f"{fk.get('referred_table')}({','.join(fk.get('referred_columns', []))})",
                    }
                    for fk in foreign_keys
                ],
            }
        )
    return docs


def rows_to_dicts(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for row in rows:
        mapping = row._mapping if hasattr(row, "_mapping") else row
        normalized: Dict[str, Any] = {}
        for key, value in mapping.items():
            if isinstance(value, Decimal):
                normalized[key] = float(value)
            elif isinstance(value, (datetime, date)):
                normalized[key] = value.isoformat()
            else:
                normalized[key] = value
        results.append(normalized)
    return results

