import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.session import build_engine
from app.main import create_app
from tests.fakes import InMemoryStorage, RecordingEmail

ROOT = Path(__file__).resolve().parent.parent
TEST_ORIGIN = "http://allowed.test"


def _test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or dotenv_values(ROOT / ".env").get(
        "TEST_DATABASE_URL"
    )
    if not url:
        pytest.exit("TEST_DATABASE_URL is not set (env var or .env)", returncode=2)
    # Guard: tests must never touch a non-disposable database.
    if not (make_url(url).database or "").endswith("_test"):
        pytest.exit("TEST_DATABASE_URL must point to a database whose name ends with '_test'", 2)
    return url


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        _env_file=None,  # tests are self-contained, never read .env
        app_env="testing",
        database_url=_test_database_url(),
        secret_key="test-secret-key-not-for-production",
        cors_allowed_origins=[TEST_ORIGIN],
        allowed_hosts=["testserver"],
        log_level="WARNING",
        rate_limit_per_minute=1000,
        password_time_cost=1,
        password_memory_kib=8,  # test-speed Argon2 parameters only
        staff_mfa_required=False,  # MFA tests turn this on explicitly
        login_max_failures=3,
        login_lockout_minutes=15,
        notify_general_emails=["ops-general@example.test"],
        notify_strategic_emails=["ops-strategic@example.test"],
        notify_partner_emails=["ops-partner@example.test"],
    )


@pytest.fixture(scope="session", autouse=True)
def migrated_database(settings: Settings) -> None:
    """Bring the (guarded, disposable) test DB to head. Upgrade only; nothing is dropped."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    previous = {k: os.environ.get(k) for k in ("DATABASE_URL", "SECRET_KEY")}
    os.environ["DATABASE_URL"] = settings.database_url.get_secret_value()
    os.environ["SECRET_KEY"] = settings.secret_key.get_secret_value()
    try:
        command.upgrade(cfg, "head")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="session")
def engine(settings: Settings, migrated_database: None) -> Iterator[Engine]:
    eng = build_engine(settings)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def concurrency_engine(settings: Settings, migrated_database: None) -> Iterator[Engine]:
    """A second disposable database (name ends in _conc_test) for tests that need real commits
    from several connections. Its rows are never deleted, so they cannot pollute other tests."""
    main = make_url(settings.database_url.get_secret_value())
    name = f"{(main.database or '').removesuffix('_test')}_conc_test"
    admin = create_engine(main, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
        ).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    url = main.set(database=name).render_as_string(hide_password=False)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    previous = {k: os.environ.get(k) for k in ("DATABASE_URL", "SECRET_KEY")}
    os.environ["DATABASE_URL"] = url
    os.environ["SECRET_KEY"] = settings.secret_key.get_secret_value()
    try:
        command.upgrade(cfg, "head")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    eng = create_engine(url, pool_size=10)
    yield eng
    eng.dispose()


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def email() -> RecordingEmail:
    return RecordingEmail()


AppFactory = Callable[..., FastAPI]


@pytest.fixture
def app_factory(
    settings: Settings, engine: Engine, storage: InMemoryStorage, email: RecordingEmail
) -> Iterator[AppFactory]:
    """Build apps whose sessions share one connection inside an outer transaction that is
    rolled back, so commits made by services never persist between tests.
    Keyword args override settings; `bot_verifier` is passed to the app."""
    with engine.connect() as connection:
        outer = connection.begin()

        def factory() -> Session:
            return Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
                autoflush=False,
                expire_on_commit=False,
            )

        def build(bot_verifier: object | None = None, **overrides: Any) -> FastAPI:
            cfg = settings.model_copy(update=overrides) if overrides else settings
            application = create_app(
                cfg,
                storage=storage,
                email_sender=email,
                bot_verifier=bot_verifier,  # type: ignore[arg-type]
            )
            application.state.sessionmaker = factory
            return application

        try:
            yield build
        finally:
            outer.rollback()


@pytest.fixture
def app(app_factory: AppFactory) -> FastAPI:
    return app_factory()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False so 500 handling is tested as a client sees it.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def db(app: FastAPI) -> Iterator[Session]:
    session: Session = app.state.sessionmaker()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """Standalone session inside an outer transaction that is always rolled back."""
    with engine.connect() as connection:
        outer = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
