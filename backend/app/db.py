"""SQLAlchemy Core persistence; MySQL/InnoDB in the app, SQLite for isolated tests."""

from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from sqlalchemy import (
    create_engine,
    event,
    MetaData,
    Table,
    Column,
    String,
    Text,
    Integer,
    Float,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
    Computed,
    text,
)
from app.config import settings


def schema(dialect):
    m = MetaData()

    def key(name="id", reference=None, primary=False, nullable=False):
        return Column(
            name,
            String(40),
            *([ForeignKey(reference)] if reference else []),
            primary_key=primary,
            nullable=nullable,
        )

    def value(name, length=120, default=None, nullable=False):
        return Column(name, String(length), nullable=nullable, server_default=default)

    def number(name, default=None):
        return Column(name, Integer, nullable=False, server_default=default)

    def content(name, default=None):
        return Column(name, Text, nullable=False, server_default=default)

    options = {
        "mysql_engine": "InnoDB",
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_unicode_ci",
    }

    def table(name, *columns):
        return Table(name, m, *columns, **options)

    table(
        "users",
        key(primary=True),
        value("email"),
        value("name", 30),
        value("password_hash", 256),
        value("role", 20, "customer"),
        UniqueConstraint("email"),
    )
    table(
        "sessions",
        Column("token_hash", String(64), primary_key=True),
        key("user_id", "users.id"),
        Column("expires_at", Float(53), nullable=False),
    )
    table(
        "products",
        key(primary=True),
        value("name"),
        value("category", 40),
        content("description"),
        number("price_cents"),
        number("stock"),
        value("image", 40),
        content("specs"),
        number("active", "1"),
        CheckConstraint("price_cents >= 0"),
        CheckConstraint("stock >= 0"),
    )
    table(
        "cart",
        key("user_id", "users.id", primary=True),
        key("product_id", "products.id", primary=True),
        number("quantity"),
        CheckConstraint("quantity BETWEEN 1 AND 99"),
    )
    table(
        "orders",
        key(primary=True),
        key("user_id", "users.id"),
        value("status", 30),
        number("total_cents"),
        value("address", 200),
        value("created_at", 40),
        value("request_key", 100),
        UniqueConstraint("user_id", "request_key"),
        Index("orders_user", "user_id", "created_at"),
    )
    table(
        "order_items",
        key("order_id", "orders.id", primary=True),
        key("product_id", "products.id", primary=True),
        value("name"),
        number("price_cents"),
        number("quantity"),
    )
    ticket_columns = [
        key(primary=True),
        key("user_id", "users.id"),
        key("order_id", "orders.id", nullable=True),
        content("reason"),
        value("status", 30, "open"),
        value("resolution", 1000, ""),
        value("created_at", 40),
    ]
    if dialect == "mysql":
        ticket_columns += [
            Column(
                "active_order_id",
                String(40),
                Computed(
                    "CASE WHEN status IN ('open','processing') THEN order_id ELSE NULL END",
                    persisted=True,
                ),
            ),
            UniqueConstraint("user_id", "active_order_id", name="one_open_ticket"),
        ]
    else:
        ticket_columns += [
            Index(
                "one_open_ticket",
                "user_id",
                "order_id",
                unique=True,
                sqlite_where=text(
                    "status IN ('open','processing') AND order_id IS NOT NULL"
                ),
            )
        ]
    table("tickets", *ticket_columns)
    table("knowledge", key(primary=True), value("title", 200), content("content"))
    table(
        "conversations",
        key(primary=True),
        key("user_id", "users.id"),
        value("title", 60),
        value("created_at", 40),
        Column("busy_until", Float(53), nullable=False, server_default="0"),
    )
    table(
        "conversation_deletions",
        key("conversation_id", "conversations.id", primary=True),
        value("deleted_at", 40),
    )
    table(
        "messages",
        Column("id", Integer, primary_key=True, autoincrement=True),
        key("conversation_id", "conversations.id"),
        value("role", 20),
        content("content"),
        content("metadata", None if dialect == "mysql" else "{}"),
        value("created_at", 40),
        Index("messages_conversation", "conversation_id", "id"),
    )
    table(
        "pending_actions",
        key(primary=True),
        key("user_id", "users.id"),
        key("conversation_id", "conversations.id"),
        value("kind", 40),
        content("payload"),
        value("summary", 300),
        value("status", 30),
        Column("result", Text, nullable=True),
        Column("expires_at", Float(53), nullable=False),
    )
    table(
        "ai_runs",
        key(primary=True),
        key("user_id", "users.id"),
        key("conversation_id", "conversations.id"),
        value("mode", 20),
        number("elapsed_ms"),
        number("llm_calls"),
        number("tool_calls"),
        number("prompt_tokens"),
        number("completion_tokens"),
        value("status", 30),
        content("trace"),
        value("created_at", 40),
    )
    table(
        "ticket_details",
        key("ticket_id", "tickets.id", primary=True),
        key("conversation_id", "conversations.id", nullable=True),
        value("category", 30),
        content("summary"),
        key("owner_id", "users.id", nullable=True),
        value("due_at", 40),
        value("updated_at", 40),
    )
    table(
        "ticket_events",
        key(primary=True),
        key("ticket_id", "tickets.id"),
        key("actor_id", "users.id"),
        value("kind", 30),
        content("content"),
        value("created_at", 40),
        Index("ticket_timeline", "ticket_id", "created_at"),
    )
    table(
        "fulfillment_events",
        key(primary=True),
        key("order_id", "orders.id"),
        value("stage", 30),
        value("detail", 300),
        value("created_at", 40),
        Index("fulfillment_timeline", "order_id", "created_at"),
    )
    table(
        "restock_plans",
        key("product_id", "products.id", primary=True),
        value("expected_at", 40),
        value("updated_at", 40),
    )
    table(
        "run_timings",
        key("run_id", "ai_runs.id", primary=True),
        Column("first_response_ms", Integer, nullable=True),
    )
    table(
        "product_events",
        key(primary=True),
        key("product_id", "products.id"),
        key("actor_id", "users.id"),
        value("kind", 30),
        content("before_data"),
        content("after_data"),
        key("action_id", "pending_actions.id", nullable=True),
        value("created_at", 40),
    )
    table(
        "schema_migrations",
        value("version", 40),
        value("applied_at", 40),
        UniqueConstraint("version"),
    )
    return m


@lru_cache(maxsize=8)
def engine_for(url):
    kwargs = {"pool_pre_ping": True, "hide_parameters": True}
    if url.startswith("sqlite:"):
        kwargs["connect_args"] = {"timeout": 15, "check_same_thread": False}
    else:
        kwargs.update(
            pool_size=5,
            max_overflow=10,
            isolation_level="READ COMMITTED",
            connect_args={
                "connect_timeout": 5,
                "read_timeout": 30,
                "write_timeout": 30,
            },
        )
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_setup(dbapi, _):
            dbapi.execute("PRAGMA foreign_keys=ON")
            dbapi.execute("PRAGMA journal_mode=WAL")

    return engine


class Row(dict):
    def __getitem__(self, key):
        return (
            tuple(self.values())[key]
            if isinstance(key, int)
            else super().__getitem__(key)
        )


class Result:
    def __init__(self, result):
        self.result = result
        self.rowcount = result.rowcount

    def fetchone(self):
        row = self.result.mappings().fetchone()
        return Row(row) if row is not None else None

    def fetchall(self):
        return [Row(r) for r in self.result.mappings().fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class Connection:
    def __init__(self, raw, write):
        self.raw, self.write = raw, write
        self.dialect = raw.dialect.name

    def execute(self, sql, parameters=()):
        # Existing business queries use positional binds; SQLAlchemy handles driver escaping.
        parts = sql.split("?")
        if len(parts) - 1 != len(parameters):
            raise ValueError("SQL bind count mismatch")
        statement = "".join(
            p + (f":p{i}" if i < len(parts) - 1 else "") for i, p in enumerate(parts)
        )
        return Result(
            self.raw.execute(
                text(statement), {f"p{i}": v for i, v in enumerate(parameters)}
            )
        )

    def lock(self, sql, parameters=()):
        return self.execute(
            sql + (" FOR UPDATE" if self.write and self.dialect == "mysql" else ""),
            parameters,
        )


@contextmanager
def connection(write=False):
    engine = engine_for(settings.database_url)
    with engine.connect() as raw:
        if write and engine.dialect.name == "sqlite":
            raw.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            yield Connection(raw, write)
            raw.commit()
        except BaseException:
            raw.rollback()
            raise


def initialize(seed_demo=None):
    engine = engine_for(settings.database_url)
    if engine.dialect.name == "sqlite":
        database = engine.url.database
        if database and database != ":memory:":
            Path(database).parent.mkdir(parents=True, exist_ok=True)
    schema(engine.dialect.name).create_all(engine)
    from app.commerce import now

    with connection(write=True) as conn:
        for version in (
            "001-commerce",
            "002-service-workspace",
            "003-product-operations",
            "004-conversation-deletion",
        ):
            if not conn.execute(
                "SELECT version FROM schema_migrations WHERE version=?", (version,)
            ).fetchone():
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?,?)", (version, now())
                )
    if settings.seed_demo if seed_demo is None else seed_demo:
        from app.seed import seed

        seed()
