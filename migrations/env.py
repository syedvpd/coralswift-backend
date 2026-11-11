"""Alembic environment. The database URL comes from app settings, never from alembic.ini."""

from alembic import context
from sqlalchemy import create_engine

# Import every module's models here (or in app/modules/<name>/models.py imported below)
# so Base.metadata is complete for autogenerate. Phase 0 has no tables.
from app.common import idempotency  # noqa: F401
from app.core.config import load_settings
from app.database.base import Base
from app.modules.admin import models as _admin  # noqa: F401
from app.modules.applications import models as _applications  # noqa: F401
from app.modules.auth import models as _auth  # noqa: F401
from app.modules.collaboration import models as _collaboration  # noqa: F401
from app.modules.content import models as _content  # noqa: F401
from app.modules.documents import models as _documents  # noqa: F401
from app.modules.engagement import models as _engagement  # noqa: F401
from app.modules.enquiries import models as _enquiries  # noqa: F401
from app.modules.media import models as _media  # noqa: F401
from app.modules.notifications import models as _notifications  # noqa: F401
from app.modules.onboarding import models as _onboarding  # noqa: F401
from app.modules.organizations import models as _organizations  # noqa: F401
from app.modules.partner_documents import models as _partner_documents  # noqa: F401
from app.modules.partners import models as _partners  # noqa: F401
from app.modules.performance import models as _performance  # noqa: F401
from app.modules.projects import models as _projects  # noqa: F401
from app.modules.review_workflow import models as _review_workflow  # noqa: F401
from app.modules.strategic import models as _strategic  # noqa: F401

target_metadata = Base.metadata
database_url = load_settings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url, connect_args={"prepare_threshold": None})
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
