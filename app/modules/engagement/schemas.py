import uuid
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.common.utilities import utcnow
from app.common.validation import Long
from app.modules.engagement.models import PrivacyRequestKind, PrivacyRequestStatus
from app.modules.enquiries.schemas import SubmitterIn


def _tz(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError("must be an IANA time zone such as America/New_York") from None
    return value


TimeZone = Annotated[str, Field(max_length=64), AfterValidator(_tz)]


class Slot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _valid(self) -> "Slot":
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start and end must include a UTC offset")
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if self.start <= utcnow():
            raise ValueError("slot must be in the future")
        return self


class MeetingRequestIn(SubmitterIn):
    """Request only: a meeting is confirmed later by staff after a real availability check."""

    purpose: Long
    preferred_slots: list[Slot] = Field(min_length=1, max_length=3)
    timezone: TimeZone


class MeetingConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    calendar_checked: bool = Field(
        description="Must be true: staff confirm availability was checked"
    )
    note: Long | None = None

    @model_validator(mode="after")
    def _valid(self) -> "MeetingConfirmIn":
        if not self.calendar_checked:
            raise ValueError("calendar availability must be checked before confirming")
        if self.start.tzinfo is None or self.end.tzinfo is None or self.end <= self.start:
            raise ValueError("start/end need a UTC offset and end must follow start")
        return self


class ReasonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Long


class NewsletterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    consent: bool

    @field_validator("consent")
    @classmethod
    def _consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent is required")
        return v


class UnsubscribeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    token: str = Field(min_length=10, max_length=64)


class PrivacyRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    kind: PrivacyRequestKind
    details: Long | None = None


class PrivacyRequestOut(BaseModel):
    id: uuid.UUID
    reference: str
    email: str
    kind: PrivacyRequestKind
    details: str | None
    status: PrivacyRequestStatus
    resolution_note: str | None
    created_at: datetime


class PrivacyUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: PrivacyRequestStatus
    resolution_note: Long | None = None
