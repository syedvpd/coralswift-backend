from sqlalchemy.orm import Session

from app.common.utilities import utcnow
from app.core.config import Settings
from app.modules.documents.constants import UploadPurpose
from app.modules.documents.service import attach_documents
from app.modules.enquiries.constants import EnquiryType
from app.modules.enquiries.models import Company
from app.modules.enquiries.service import Created, create_enquiry
from app.modules.partners.models import PartnerApplication
from app.modules.partners.schemas import PartnerApplicationIn


def create_partner_application(
    db: Session, settings: Settings, data: PartnerApplicationIn
) -> Created:
    company = Company(
        legal_name=data.company_name,
        website=data.website,
        year_established=data.year_established,
        registered_address=data.registered_address,
        country=data.company_country,
    )
    created = create_enquiry(
        db,
        settings,
        enquiry_type=EnquiryType.PARTNER,
        submitter=data,
        company=company,
        subject="Partner application",
        message=None,
    )
    db.add(
        PartnerApplication(
            enquiry_id=created.enquiry.id,
            company_id=company.id,
            preferred_engagement_pathway=data.preferred_engagement_pathway,
            workforce_range=data.workforce_range,
            turnover_range=data.turnover_range,
            service_categories=[c.value for c in data.service_categories],
            infrastructure_summary=data.infrastructure_summary,
            client_experience=data.client_experience,
            client_references=[r.model_dump() for r in data.client_references],
            submitted_at=utcnow(),
        )
    )
    created.out.documents_attached = attach_documents(
        db,
        enquiry_id=created.enquiry.id,
        document_ids=data.document_ids,
        purpose=UploadPurpose.PARTNER_EVIDENCE,
        settings=settings,
    )
    return created
