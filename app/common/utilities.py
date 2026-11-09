from datetime import UTC, datetime


def utcnow() -> datetime:
    """Timezone-aware UTC now. Use this everywhere; never naive datetimes."""
    return datetime.now(UTC)
