from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.documents.constants import UploadPurpose
from app.modules.documents.service import attach_documents
from app.modules.enquiries.constants import EnquiryType
from app.modules.enquiries.service import Created, create_enquiry
from app.modules.projects.models import ProjectEnquiry
from app.modules.projects.schemas import ProjectEnquiryIn


def create_project_enquiry(db: Session, settings: Settings, data: ProjectEnquiryIn) -> Created:
    created = create_enquiry(
        db,
        settings,
        enquiry_type=EnquiryType.PROJECT,
        submitter=data,
        company=None,
        subject=data.project_category.value,
        message=data.requirement_summary,
    )
    db.add(
        ProjectEnquiry(
            enquiry_id=created.enquiry.id,
            project_category=data.project_category,
            requirement_summary=data.requirement_summary,
            scope=data.scope,
            expected_timeline=data.expected_timeline,
            estimated_volume=data.estimated_volume,
            geography=data.geography,
            security_constraints=data.security_constraints,
        )
    )
    created.out.documents_attached = attach_documents(
        db,
        enquiry_id=created.enquiry.id,
        document_ids=data.document_ids,
        purpose=UploadPurpose.PROJECT_ATTACHMENT,
        settings=settings,
    )
    return created
