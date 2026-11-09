from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database.dependencies import get_db

ROOT = Path(__file__).resolve().parents[2]


def test_real_database_connection(db_session: Session) -> None:
    assert db_session.execute(text("SELECT 1")).scalar_one() == 1


def test_session_timezone_is_utc(db_session: Session) -> None:
    assert db_session.execute(text("SHOW timezone")).scalar_one().lower() == "utc"


def test_changes_roll_back_between_tests(db_session: Session) -> None:
    db_session.execute(text("CREATE TEMP TABLE t_iso (x int)"))
    db_session.execute(text("INSERT INTO t_iso VALUES (1)"))
    assert db_session.execute(text("SELECT count(*) FROM t_iso")).scalar_one() == 1


def test_temp_table_from_previous_test_is_gone(db_session: Session) -> None:
    exists = db_session.execute(text("SELECT to_regclass('pg_temp.t_iso')")).scalar_one()
    assert exists is None


def test_get_db_yields_and_closes_session(app: FastAPI) -> None:
    class FakeRequest:
        pass

    req = FakeRequest()
    req.app = app  # type: ignore[attr-defined]
    gen = get_db(req)  # type: ignore[arg-type]
    session = next(gen)
    assert session.execute(text("SELECT 1")).scalar_one() == 1
    gen.close()
    assert not session.in_transaction()


def test_alembic_has_single_head() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1
