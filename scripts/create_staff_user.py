"""Create a staff (reviewer / super administrator) account. The only way staff accounts are made.

Usage (password is read from the STAFF_PASSWORD env var or prompted; never put it on the command line):
    python scripts/create_staff_user.py --email a@b.com --name "Full Name" --role partner_reviewer

Uses DATABASE_URL from the environment/.env. Point it at the intended database deliberately.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import load_settings  # noqa: E402
from app.database.session import build_engine, build_sessionmaker  # noqa: E402
from app.modules.auth.constants import StaffRole  # noqa: E402
from app.modules.auth.service import create_staff_user  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", required=True, choices=[r.value for r in StaffRole])
    args = parser.parse_args()
    password = os.environ.get("STAFF_PASSWORD") or getpass.getpass("Password: ")
    settings = load_settings()
    engine = build_engine(settings)
    with build_sessionmaker(engine)() as db:
        user = create_staff_user(
            db,
            settings,
            email=args.email,
            full_name=args.name,
            role=StaffRole(args.role),
            password=password,
        )
        db.commit()
        print(f"created staff user {user.id} ({user.staff_role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
