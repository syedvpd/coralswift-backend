import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.utilities import utcnow
from app.common.validation import (
    BusinessEmail,
    Country,
    Long,
    Medium,
    Name,
    Phone,
    Short,
)
from app.modules.partners.constants import ServiceCategory
from app.modules.partners.schemas import ClientReference, Url


class AuthorizedContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    designation: Name
    email: BusinessEmail
    phone: Phone


class ProfileUpdate(BaseModel):
    """Partial update: only fields present in the request change. `expected_version` (optional)
    makes the update fail with 409 if someone else changed the profile meanwhile."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = Field(default=None, ge=0)
    legal_name: Short | None = None
    registration_number: Short | None = None
    year_established: int | None = Field(default=None, ge=1800)
    employee_count: int | None = Field(default=None, ge=0, le=10_000_000)
    annual_turnover_inr_crore: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    registered_address: Medium | None = None
    country: Country | None = None
    website: Url | None = None
    service_categories: list[ServiceCategory] | None = Field(default=None, max_length=12)
    technical_capabilities: Long | None = None
    infrastructure_summary: Long | None = None
    business_description: Long | None = None
    client_references: list[ClientReference] | None = Field(default=None, max_length=10)
    authorized_contacts: list[AuthorizedContact] | None = Field(default=None, max_length=10)

    @field_validator("year_established")
    @classmethod
    def _not_future(cls, value: int | None) -> int | None:
        if value is not None and value > utcnow().year:
            raise ValueError("cannot be in the future")
        return value


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    status: str
    registration_number: str | None
    year_established: int | None
    employee_count: int | None
    annual_turnover_inr_crore: Decimal | None
    registered_address: str | None
    country: str | None
    website: str | None
    service_categories: list[str] | None
    technical_capabilities: str | None
    infrastructure_summary: str | None
    business_description: str | None
    client_references: list[dict[str, Any]] | None
    authorized_contacts: list[dict[str, Any]] | None
    profile_version: int


class CompletionOut(BaseModel):
    percent: int
    missing_fields: list[str]
    complete: bool


class RevisionOut(BaseModel):
    version: int
    changed_by: uuid.UUID
    changes: dict[str, Any]
    created_at: datetime
