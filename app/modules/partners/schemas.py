from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.common.utilities import utcnow
from app.common.validation import Country, Long, Medium, Name, Short
from app.modules.enquiries.schemas import DocumentIds, SubmitterIn
from app.modules.partners.constants import (
    EngagementPathway,
    ServiceCategory,
    TurnoverRange,
    WorkforceRange,
)


def _http_url(value: str) -> str:
    if not value.startswith(("http://", "https://")) or len(value) > 300 or "\x00" in value:
        raise ValueError("must be an http(s) URL up to 300 characters")
    return value


Url = Annotated[str, AfterValidator(_http_url)]


class ClientReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    organization: Short
    contact: Short = Field(description="Email or phone of the referee")


class PartnerApplicationIn(SubmitterIn):
    """Values are recorded for human review. They never trigger approval or rejection."""

    company_name: Short = Field(description="Legal company name")
    designation: Name
    website: Url | None = None
    year_established: int = Field(ge=1800)
    registered_address: Medium
    company_country: Country
    preferred_engagement_pathway: EngagementPathway
    workforce_range: WorkforceRange
    turnover_range: TurnoverRange
    service_categories: list[ServiceCategory] = Field(min_length=1, max_length=12)
    infrastructure_summary: Long
    client_experience: Long
    client_references: list[ClientReference] = Field(min_length=2, max_length=5)
    document_ids: DocumentIds = Field(
        default_factory=list, description="Evidence from POST /documents/upload"
    )

    @field_validator("year_established")
    @classmethod
    def _not_future(cls, value: int) -> int:
        if value > utcnow().year:
            raise ValueError("cannot be in the future")
        return value

    @field_validator("service_categories")
    @classmethod
    def _unique(cls, value: list[ServiceCategory]) -> list[ServiceCategory]:
        return list(dict.fromkeys(value))
