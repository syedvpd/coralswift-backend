import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

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
from app.modules.organizations.constants import CompanyType, OperatingModel
from app.modules.partners.constants import ServiceCategory
from app.modules.partners.schemas import ClientReference, Url


class AuthorizedContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    designation: Name
    email: BusinessEmail
    phone: Phone


class OfficeLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: Short
    state: Short | None = None
    country: Country | None = None
    address: Medium | None = None


class AdditionalContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    designation: Name | None = None
    email: BusinessEmail
    phone: Phone | None = None


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
    trading_name: Short | None = None
    company_type: CompanyType | None = None
    state: Short | None = None
    city: Short | None = None
    primary_industry: Short | None = None
    competencies: list[Short] | None = Field(default=None, max_length=20)
    operating_model: OperatingModel | None = None
    coverage: list[Short] | None = Field(default=None, max_length=30)
    years_of_experience: int | None = Field(default=None, ge=0, le=200)
    offices: list[OfficeLocation] | None = Field(default=None, max_length=20)
    workforce: dict[Annotated[str, Field(min_length=1, max_length=40)], int] | None = Field(
        default=None, description="headcount by function, e.g. {'engineering': 40}"
    )
    financial_period: Short | None = Field(default=None, description="e.g. FY2025-26")
    additional_contacts: list[AdditionalContact] | None = Field(default=None, max_length=10)

    @field_validator("workforce")
    @classmethod
    def _workforce(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is not None and (
            len(value) > 20 or any(v < 0 or v > 10_000_000 for v in value.values())
        ):
            raise ValueError("at most 20 functions, each between 0 and 10,000,000")
        return value

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
    trading_name: str | None = None
    company_type: CompanyType | None = None
    state: str | None = None
    city: str | None = None
    primary_industry: str | None = None
    competencies: list[str] | None = None
    operating_model: OperatingModel | None = None
    coverage: list[str] | None = None
    years_of_experience: int | None = None
    offices: list[dict[str, Any]] | None = None
    workforce: dict[str, Any] | None = None
    financial_period: str | None = None
    additional_contacts: list[dict[str, Any]] | None = None


class CompletionOut(BaseModel):
    percent: int
    missing_fields: list[str]
    complete: bool


class EditableFieldOut(BaseModel):
    """direct_update: a still-empty field can be filled directly. approval_required: changing or
    clearing an existing value needs a change request (409 CHANGE_REQUEST_REQUIRED otherwise)."""

    name: str
    direct_update: bool
    approval_required: bool
    nullable: bool
    null_clears: bool


class RevisionOut(BaseModel):
    version: int
    changed_by: uuid.UUID
    changes: dict[str, Any]
    created_at: datetime
