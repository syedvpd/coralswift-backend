"""Run scheduled maintenance once (cron / scheduler): idempotency cleanup, SLA escalation, expiry
reminders, retention purge, approved content publication, notification dispatch. Uses DATABASE_URL,
STORAGE_* and EMAIL_* from the environment, so point it at the intended environment deliberately.

`--dry-run` only counts what each job would act on, inside a READ ONLY transaction; it deletes,
changes, queues and sends nothing."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.database.session import build_engine, build_sessionmaker  # noqa: E402
from app.integrations.email import build_email_sender  # noqa: E402
from app.integrations.storage import build_storage  # noqa: E402
from app.modules.admin.maintenance import preview, run_all  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run scheduled maintenance once.")
    parser.add_argument(
        "--dry-run", action="store_true", help="count affected rows only; change nothing"
    )
    args = parser.parse_args(argv)
    settings = load_settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings)
    if args.dry_run:
        print({"dry_run": True, **preview(build_sessionmaker(engine), settings)})
        return 0
    result = run_all(
        build_sessionmaker(engine), settings, build_storage(settings), build_email_sender(settings)
    )
    logging.getLogger("app.maintenance").info("maintenance finished", extra=result)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
