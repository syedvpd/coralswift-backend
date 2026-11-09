from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.documents.constants import Classification, UploadPurpose
from app.modules.documents.service import attach_documents
from app.modules.enquiries.constants import EnquiryType
from app.modules.enquiries.service import Created, create_enquiry
from app.modules.strategic.models import StrategicEnquiry
from app.modules.strategic.schemas import StrategicEnquiryIn


def create_strategic_enquiry(db: Session, settings: Settings, data: StrategicEnquiryIn) -> Created:
    created = create_enquiry(
        db,
        settings,
        enquiry_type=EnquiryType.STRATEGIC,
        submitter=data,
        company=None,
        subject="Strategic discussion",
        message=None,  # confidential text lives only in strategic_enquiries
    )
    db.add(
        StrategicEnquiry(
            enquiry_id=created.enquiry.id,
            discussion_type=data.discussion_type,
            business_overview=data.business_overview,
            confidential_summary=data.confidential_summary,
            access_classification=Classification.CONFIDENTIAL,
        )
    )
    created.out.documents_attached = attach_documents(
        db,
        enquiry_id=created.enquiry.id,
        document_ids=data.document_ids,
        purpose=UploadPurpose.STRATEGIC_ATTACHMENT,
        settings=settings,
    )
    return created
