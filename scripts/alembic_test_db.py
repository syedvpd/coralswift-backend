"""Run an alembic command against the LOCAL disposable test database only.

Usage: python scripts/alembic_test_db.py upgrade head | current | check | revision --autogenerate -m "msg"

Refuses to run unless TEST_DATABASE_URL points to localhost and a database named *_test, so a
shared/development database can never be touched by accident.
"""

import os
import sys
from pathlib import Path

from alembic.config import main as alembic_main
from dotenv import dotenv_values
from sqlalchemy import make_url

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    url = os.environ.get("TEST_DATABASE_URL") or dotenv_values(ROOT / ".env").get(
        "TEST_DATABASE_URL"
    )
    if not url:
        print("TEST_DATABASE_URL is not set", file=sys.stderr)
        return 2
    parsed = make_url(url)
    if parsed.host not in ("localhost", "127.0.0.1", "::1") or not (parsed.database or "").endswith(
        "_test"
    ):
        print("refusing: TEST_DATABASE_URL must be a local *_test database", file=sys.stderr)
        return 2
    os.environ["DATABASE_URL"] = url
    os.environ.setdefault("SECRET_KEY", "alembic-local-only-not-a-real-secret")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    alembic_main(argv=sys.argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
