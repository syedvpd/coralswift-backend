import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.common.validation import BusinessEmail, Country, Message, Name, Phone, Short
from app.modules.enquiries.constants import ContactTopic, EnquiryStatus, EnquiryType


class SubmitterIn(BaseModel):
    """Contact + consent block shared by every public form. Unknown fields are rejected so the
    API cannot silently collect data nobody designed for (e.g. patient or bank details)."""

    model_config = ConfigDict(extra="forbid")

    full_name: Name
    designation: Name | None = None
    business_email: BusinessEmail
    phone: Phone
    country: Country
    company_name: Short | None = None
    # Optional lead source, e.g. a campaign tag from the website (PRD s.15B)
    lead_source: (
        Annotated[str, StringConstraints(max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")] | None
    ) = None
    privacy_consent: bool = Field(description="Must be true: the user accepted the privacy notice")

    @field_validator("privacy_consent")
    @classmethod
    def _consent_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Privacy consent is required")
        return value


DocumentIds = Annotated[list[uuid.UUID], Field(max_length=20)]


class ContactEnquiryIn(SubmitterIn):
    enquiry_type: ContactTopic
    message: Message


class SubmissionOut(BaseModel):
    reference_number: str
    lookup_token: str = Field(description="Keep it: needed with the reference to check status")
    enquiry_type: EnquiryType
    status: EnquiryStatus
    submitted_at: datetime
    documents_attached: int = 0


class StatusOut(BaseModel):
    reference_number: str
    enquiry_type: EnquiryType
    status: EnquiryStatus
    submitted_at: datetime
