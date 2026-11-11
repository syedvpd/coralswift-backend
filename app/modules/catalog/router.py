"""Read-only public reference data derived from the PRD: illustrative project categories (s.9),
proposed partner criteria and pathways (s.8), and confirmed contact details (s.28)."""

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.common.responses import ApiResponse, ok
from app.database.dependencies import DbSession
from app.modules.admin import settings_service as cfg
from app.modules.partners.constants import EngagementPathway
from app.modules.projects.constants import ProjectCategory, category_group

router = APIRouter(tags=["catalog"])

ILLUSTRATIVE_NOTE = "Illustrative category only: not a live, awarded or guaranteed project."
CHECKLIST = [
    "Company registration proof",
    "Three-year operating history",
    "Employee-strength evidence",
    "Latest financial statements",
    "Service portfolio",
    "Infrastructure summary",
    "Two client references",
    "Authorized contact details",
]


class ProjectCategoryOut(BaseModel):
    value: str
    group: str  # it | non_it
    illustrative: bool
    label_note: str


class CriterionOut(BaseModel):
    key: str
    threshold: str
    applies_to: str | list[str]  # text until the owner confirms the pathways


class PartnerCriteriaOut(BaseModel):
    status: str
    disclaimer: str
    criteria: list[CriterionOut]
    pathways: list[str]
    submission_checklist: list[str]


def _cache(response: Response) -> None:
    response.headers["Cache-Control"] = "public, max-age=300"


@router.get(
    "/catalog/project-categories",
    response_model=ApiResponse[list[ProjectCategoryOut]],
    summary="Project categories, always labelled illustrative (PRD s.9, s.28)",
)
def project_categories(response: Response) -> ApiResponse[list[ProjectCategoryOut]]:
    _cache(response)
    return ok(
        [
            ProjectCategoryOut(
                value=c.value,
                group=category_group(c),
                illustrative=True,
                label_note=ILLUSTRATIVE_NOTE,
            )
            for c in ProjectCategory
        ]
    )


@router.get(
    "/catalog/partner-criteria",
    response_model=ApiResponse[PartnerCriteriaOut],
    summary="Proposed screening criteria, pathways and submission checklist (PRD s.8)",
)
def partner_criteria(response: Response) -> ApiResponse[PartnerCriteriaOut]:
    _cache(response)
    return ok(
        {
            "status": "proposed",
            "disclaimer": "Proposed screening criteria only. Not a promise of merger approval, project award or guaranteed allocation. Exceptions are recorded only through the approved internal process.",
            "criteria": [
                {
                    "key": "business_age",
                    "threshold": "At least 3 years of established operations",
                    "applies_to": "to be confirmed by the business owner",
                },
                {
                    "key": "workforce",
                    "threshold": "Minimum 50 employed personnel, supported by payroll or statutory records",
                    "applies_to": "to be confirmed by the business owner",
                },
                {
                    "key": "annual_turnover",
                    "threshold": "Minimum INR 2 crore, supported by audited statements or equivalent",
                    "applies_to": [EngagementPathway.DIRECT_PROJECT_ENGAGEMENT.value],
                },
                {
                    "key": "additional_assessment",
                    "threshold": "Delivery history, capabilities, compliance, data security, management strength, client references, commercial fit",
                    "applies_to": "all pathways",
                },
            ],
            "pathways": [p.value for p in EngagementPathway],
            "submission_checklist": CHECKLIST,
        }
    )


@router.get(
    "/site/contact",
    response_model=ApiResponse[dict[str, str]],
    summary="Verified contact details only; unconfirmed or omitted items are absent",
)
def site_contact(response: Response, db: DbSession) -> ApiResponse[dict[str, str]]:
    _cache(response)
    return ok({i: v for i in cfg.CONTACT_ITEMS if (v := cfg.get(db, f"contact.{i}"))})
