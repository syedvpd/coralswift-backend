from pydantic import Field

from app.common.validation import Long, Short
from app.modules.enquiries.schemas import DocumentIds, SubmitterIn
from app.modules.projects.constants import ProjectCategory


class ProjectEnquiryIn(SubmitterIn):
    """Business-level requirement only. Do NOT include patient, health or bank-account data."""

    company_name: Short
    project_category: ProjectCategory = Field(description="Enquiry category, not a live project")
    requirement_summary: Long
    scope: Long
    expected_timeline: Short
    estimated_volume: Short | None = None
    geography: Short
    security_constraints: Long | None = None
    document_ids: DocumentIds = Field(
        default_factory=list, description="From POST /documents/upload"
    )
