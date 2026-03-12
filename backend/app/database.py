"""SQLAlchemy database setup"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().database_url,
    connect_args={"check_same_thread": False},  # SQLite
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """Additive schema migrations — safe to run on every startup."""
    # Multi-tenancy scaffolding (phase 1): stamp every entity row with tenant_id.
    # Today it's always 'default' (single owner). When multi-tenancy ships,
    # inserts switch to current_user.id from the JWT and queries filter by it.
    _TENANT_TABLES = [
        "positions", "themes", "watchlist_items", "alerts",
        "alpha_insights", "alpha_sources",
    ]
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        for table in _TENANT_TABLES:
            cols = [row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]
            if "tenant_id" not in cols:
                cur.execute(
                    f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'"
                )
        raw.commit()
    finally:
        raw.close()
