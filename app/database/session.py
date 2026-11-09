"""Engine and session factory, built per app instance (no import-time globals)."""

from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    # Lazy: no connection is opened until first use, so startup never blocks on the DB.
    engine = create_engine(
        settings.database_url.get_secret_value(),
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
        # prepare_threshold=None: no server-side prepared statements (poolers in transaction mode).
        connect_args={"connect_timeout": 10, "prepare_threshold": None},
    )

    # Not a startup "options" param: PgBouncer/Supabase poolers reject those.
    @event.listens_for(engine, "connect")
    def _utc(dbapi_conn: Any, _: Any) -> None:
        with dbapi_conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC'")
        dbapi_conn.commit()

    return engine


def build_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
