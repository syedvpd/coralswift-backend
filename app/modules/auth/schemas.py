import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.validation import EmailAddress, Name
from app.modules.auth.constants import StaffRole, UserStatus, UserType


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailAddress
    password: str = Field(min_length=1, max_length=256)


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=10, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AcceptInvitationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class PasswordResetRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailAddress


class PasswordResetConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class OrganizationRef(BaseModel):
    id: uuid.UUID
    legal_name: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None = None
    user_type: UserType
    account_status: UserStatus
    staff_role: StaffRole | None = None
    partner_role: str | None = None  # owner | member (partner accounts)
    permissions: list[str] = Field(default_factory=list)  # partner permissions, e.g. team.manage
    organization: OrganizationRef | None = None
    last_login_at: datetime | None = None


class ProfileUpdateIn(BaseModel):
    """Only the fields you send change. `phone` null clears it; the name cannot be cleared."""

    model_config = ConfigDict(extra="forbid")

    full_name: Name | None = None
    phone: str | None = Field(default=None, pattern=r"^\+[0-9]{7,15}$")

    @model_validator(mode="after")
    def _something_to_change(self) -> "ProfileUpdateIn":
        if not self.model_fields_set:
            raise ValueError("send full_name and/or phone")
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be cleared")
        return self


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_used_at: datetime | None
    user_agent: str | None
    current: bool
    expires_at: datetime | None = None  # when the refresh token stops working
