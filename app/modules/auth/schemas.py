import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.auth.constants import StaffRole, UserType


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=10, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    # Staff must finish MFA before protected routes work (see /auth/mfa/*).
    mfa_required: bool = False
    mfa_enrollment_required: bool = False


class AcceptInvitationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class PasswordResetRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=1, max_length=256)


class OrganizationRef(BaseModel):
    id: uuid.UUID
    legal_name: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    user_type: UserType
    staff_role: StaffRole | None = None
    organization: OrganizationRef | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_used_at: datetime | None
    user_agent: str | None
    current: bool


class MfaEnrollOut(BaseModel):
    secret: str = Field(description="Base32 secret for authenticator apps; shown once")
    otpauth_uri: str


class MfaCodeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class MfaVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    recovery_code: str | None = Field(default=None, min_length=10, max_length=10)


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str] = Field(description="Single-use; shown once. Store them safely.")
