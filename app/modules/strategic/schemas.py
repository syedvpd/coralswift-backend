from pydantic import Field, field_validator

from app.common.validation import Long, Name, Short
from app.modules.enquiries.schemas import DocumentIds, SubmitterIn
from app.modules.strategic.constants import DiscussionType


class StrategicEnquiryIn(SubmitterIn):
    """Confidential. Free-text fields are never logged or emailed."""

    company_name: Short
    designation: Name
    discussion_type: DiscussionType
    business_overview: Long
    confidential_summary: Long
    authorized_representative: bool = Field(
        description="Sender confirms they are authorised to make this enquiry"
    )
    document_ids: DocumentIds = Field(default_factory=list)

    @field_validator("authorized_representative")
    @classmethod
    def _must_confirm(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Authorised representative confirmation is required")
        return value
