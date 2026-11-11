"""Central v1 router. Phase 1+ modules register their routers here."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.common.responses import ApiResponse, ok
from app.core.config import Settings, get_settings
from app.modules.admin.feed import router as admin_feed_router
from app.modules.admin.followups_router import router as admin_followups_router
from app.modules.admin.ops_router import router as admin_ops_router
from app.modules.admin.org_history_router import router as admin_org_history_router
from app.modules.admin.people_router import router as admin_people_router
from app.modules.admin.reference_router import router as admin_reference_router
from app.modules.admin.router import router as admin_router
from app.modules.applications.router import router as applications_router
from app.modules.auth.router import router as auth_router
from app.modules.catalog.router import router as catalog_router
from app.modules.collaboration import partner_router as collab_partner
from app.modules.collaboration.assignment_router import router as bdm_assignment_router
from app.modules.collaboration.staff_router import router as collab_staff_router
from app.modules.content.router import admin as content_admin_router
from app.modules.content.router import claims as content_claims_router
from app.modules.content.router import public as content_public_router
from app.modules.documents.router import router as documents_router
from app.modules.engagement.router import admin as engagement_admin_router
from app.modules.engagement.router import partner as engagement_partner_router
from app.modules.engagement.router import public as engagement_public_router
from app.modules.enquiries.router import router as enquiries_router
from app.modules.media import router as media_routes
from app.modules.messaging.router import router as messaging_router
from app.modules.notifications import webhook as email_webhook
from app.modules.onboarding import router as onboarding_routes
from app.modules.organizations.extras import admin as profile_changes_admin_router
from app.modules.organizations.extras import partner as partner_dashboard_router
from app.modules.organizations.router import router as organizations_router
from app.modules.partner_documents.requests import (
    partner_router as document_requests_partner_router,
)
from app.modules.partner_documents.requests import staff_router as document_requests_staff_router
from app.modules.partner_documents.router import router as partner_documents_router
from app.modules.partner_team import router as team_routes
from app.modules.partners.router import router as partners_router
from app.modules.performance import router as performance_routes
from app.modules.projects.router import router as projects_router
from app.modules.review_workflow import comms_router as workflow_comms
from app.modules.review_workflow import router as workflow_routes
from app.modules.reviews.router import router as reviews_router
from app.modules.strategic.router import router as strategic_router

api_router = APIRouter()
for _router in (
    enquiries_router,
    projects_router,
    partners_router,
    strategic_router,
    documents_router,
    auth_router,
    admin_router,
    admin_ops_router,
    admin_org_history_router,
    admin_followups_router,
    admin_feed_router,
    admin_people_router,
    admin_reference_router,
    catalog_router,
    content_admin_router,
    content_claims_router,
    content_public_router,
    engagement_admin_router,
    engagement_public_router,
    engagement_partner_router,
    applications_router,
    messaging_router,
    organizations_router,
    partner_dashboard_router,
    profile_changes_admin_router,
    partner_documents_router,
    document_requests_partner_router,
    document_requests_staff_router,
    reviews_router,
    collab_staff_router,
    bdm_assignment_router,
    email_webhook.router,
    performance_routes.partner,
    performance_routes.staff,
    media_routes.admin,
    media_routes.public,
    workflow_routes.router,
    workflow_routes.enquiry,
    workflow_comms.enquiry,
    workflow_comms.documents,
    team_routes.team,
    team_routes.staff_team,
    team_routes.prefs,
    team_routes.closure,
    onboarding_routes.partner,
    onboarding_routes.staff_router,
    onboarding_routes.template_router,
    collab_partner.projects,
    collab_partner.inbox,
    collab_partner.discussions,
    collab_partner.meetings,
    collab_partner.follow_ups,
):
    api_router.include_router(_router)


@api_router.get("/meta", tags=["meta"], response_model=ApiResponse[dict[str, str]])
def meta(settings: Annotated[Settings, Depends(get_settings)]) -> ApiResponse[dict[str, str]]:
    return ok({"name": settings.app_name, "version": settings.app_version, "api": "v1"})
