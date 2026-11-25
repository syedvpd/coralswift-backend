"""Unit and RBAC tests for the 10-step Project Exchange Platform workflow."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.main import create_app
from app.modules.auth.constants import StaffRole, UserType
from app.modules.auth.dependencies import StaffContext
from app.modules.auth.permissions import permissions_for, role_matrix
from app.modules.delivery_governance import service as deliv_service
from app.modules.delivery_governance.schemas import ContractSignIn
from app.modules.opportunities import service as opp_service
from app.modules.opportunities.constants import OpportunityStatus, OpportunityVisibility
from app.modules.opportunities.models import ProjectOpportunity
from app.modules.opportunities.schemas import (
    CriteriaMatrixIn,
    CriterionIn,
    OpportunityPublishIn,
    OpportunityStructureIn,
)


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Override DB migration fixture for isolated unit testing."""
    return None


def _staff_ctx(role: StaffRole) -> StaffContext:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.staff_role = role
    user.user_type = UserType.STAFF
    session = MagicMock()
    return StaffContext(user=user, session=session)


def _test_app():
    settings = Settings(
        _env_file=None,
        app_env="testing",
        database_url="postgresql+psycopg://x:x@localhost:5432/x_test",
        secret_key="x" * 50,
        allowed_hosts=["testserver"],
        cors_allowed_origins=["http://localhost:3000"],
    )
    return create_app(settings)


def test_new_staff_roles_and_permission_matrix() -> None:
    app = _test_app()
    matrix = role_matrix(app)

    # All 10 roles exist in matrix
    for role in StaffRole:
        assert role.value in matrix

    # Sourcing Manager has opportunities & contracts, not invoices or audit
    sourcing_eps = {
        (e["method"], e["path"])
        for m in permissions_for(app, UserType.STAFF, StaffRole.SOURCING_MANAGER)["modules"]
        for e in m["endpoints"]
    }
    assert ("POST", "/api/v1/admin/opportunities") in sourcing_eps
    assert ("POST", "/api/v1/admin/opportunities/{opp_id}/publish") in sourcing_eps
    assert ("POST", "/api/v1/admin/opportunities/{opp_id}/shortlist") in sourcing_eps
    assert ("POST", "/api/v1/admin/opportunities/{opp_id}/shortlist/decision") not in sourcing_eps
    assert ("GET", "/api/v1/admin/invoices") not in sourcing_eps
    assert ("GET", "/api/v1/admin/audit") not in sourcing_eps

    # Approver has shortlist decision & award, not criteria creation or invoices
    approver_eps = {
        (e["method"], e["path"])
        for m in permissions_for(app, UserType.STAFF, StaffRole.APPROVER)["modules"]
        for e in m["endpoints"]
    }
    assert ("POST", "/api/v1/admin/opportunities/{opp_id}/shortlist/decision") in approver_eps
    assert ("POST", "/api/v1/admin/opportunities/{opp_id}/award") in approver_eps
    assert ("POST", "/api/v1/admin/opportunities") not in approver_eps
    assert ("GET", "/api/v1/admin/invoices") not in approver_eps

    # Delivery Manager has deliverable review, milestone comments, and project closure
    delivery_eps = {
        (e["method"], e["path"])
        for m in permissions_for(app, UserType.STAFF, StaffRole.DELIVERY_MANAGER)["modules"]
        for e in m["endpoints"]
    }
    assert ("POST", "/api/v1/admin/deliverables/{deliverable_id}/review") in delivery_eps
    assert ("POST", "/api/v1/admin/milestones/{milestone_id}/comments") in delivery_eps
    assert ("POST", "/api/v1/admin/projects/{project_id}/close") in delivery_eps

    # Finance has invoice list & status update, not opportunities
    finance_eps = {
        (e["method"], e["path"])
        for m in permissions_for(app, UserType.STAFF, StaffRole.FINANCE)["modules"]
        for e in m["endpoints"]
    }
    assert ("GET", "/api/v1/admin/invoices") in finance_eps
    assert ("POST", "/api/v1/admin/invoices/{invoice_id}/status") in finance_eps
    assert ("POST", "/api/v1/admin/opportunities") not in finance_eps

    # Auditor has read-only access to /admin/audit*
    auditor_eps = {
        (e["method"], e["path"])
        for m in permissions_for(app, UserType.STAFF, StaffRole.AUDITOR)["modules"]
        for e in m["endpoints"]
    }
    assert ("GET", "/api/v1/admin/audit") in auditor_eps
    assert ("GET", "/api/v1/admin/audit/actions") in auditor_eps
    assert ("GET", "/api/v1/admin/audit/{activity_id}") in auditor_eps
    assert ("GET", "/api/v1/admin/audit.csv") in auditor_eps
    assert ("POST", "/api/v1/admin/invoices/{invoice_id}/status") not in auditor_eps

    # Compliance Officer has compliance screening & reviewer routes
    compliance_eps = {
        (e["method"], e["path"])
        for m in permissions_for(app, UserType.STAFF, StaffRole.COMPLIANCE_OFFICER)["modules"]
        for e in m["endpoints"]
    }
    assert (
        "PUT",
        "/api/v1/admin/compliance/organizations/{organization_id}/screening",
    ) in compliance_eps
    assert ("GET", "/api/v1/reviewer/applications") in compliance_eps

    # Partner has discovery, proposals, contracts, deliverables, closure, invoices
    partner_eps = {
        (e["method"], e["path"])
        for m in permissions_for(app, UserType.PARTNER, None)["modules"]
        for e in m["endpoints"]
    }
    assert ("GET", "/api/v1/partner/opportunities") in partner_eps
    assert ("PUT", "/api/v1/partner/opportunities/{opp_id}/proposals") in partner_eps
    assert ("POST", "/api/v1/partner/proposals/{proposal_id}/submit") in partner_eps
    assert ("POST", "/api/v1/partner/contracts/{contract_id}/sign") in partner_eps
    assert ("POST", "/api/v1/partner/milestones/{milestone_id}/deliverables") in partner_eps
    assert ("POST", "/api/v1/partner/invoices") in partner_eps
    assert ("GET", "/api/v1/partner/projects/{project_id}/closure") in partner_eps


def test_opportunity_structuring_budget_validation() -> None:
    db = MagicMock()
    opp = ProjectOpportunity(
        id=uuid.uuid4(),
        reference="OPP-2026-0001",
        title="ERP Rollout",
        category="it_services",
        status=OpportunityStatus.INTAKE,
        created_by=uuid.uuid4(),
    )
    db.execute.return_value.scalar_one_or_none.return_value = opp
    staff = _staff_ctx(StaffRole.SOURCING_MANAGER)

    with pytest.raises(AppError) as exc:
        opp_service.structure_opportunity(
            db,
            staff,
            opp.id,
            OpportunityStructureIn(
                scope="Full SAP rollout",
                required_skills=["SAP", "Python"],
                budget_min=Decimal("500000"),
                budget_max=Decimal("100000"),
                expected_timeline="6 months",
                submission_deadline=datetime.now(UTC) + timedelta(days=14),
            ),
        )
    assert exc.value.code == "INVALID_BUDGET"


def test_opportunity_publish_visibility_rules() -> None:
    db = MagicMock()
    opp = ProjectOpportunity(
        id=uuid.uuid4(),
        reference="OPP-2026-0002",
        title="Cloud Migration",
        category="cloud",
        status=OpportunityStatus.STRUCTURING,
        created_by=uuid.uuid4(),
    )
    db.execute.return_value.scalar_one_or_none.return_value = opp
    staff = _staff_ctx(StaffRole.SOURCING_MANAGER)

    with pytest.raises(AppError) as exc1:
        opp_service.publish_opportunity(
            db,
            staff,
            opp.id,
            OpportunityPublishIn(visibility=OpportunityVisibility.INVITE_ONLY),
        )
    assert exc1.value.code == "INVITATIONS_REQUIRED"

    with pytest.raises(AppError) as exc2:
        opp_service.publish_opportunity(
            db,
            staff,
            opp.id,
            OpportunityPublishIn(visibility=OpportunityVisibility.CATEGORY_TARGETED),
        )
    assert exc2.value.code == "TARGET_CATEGORIES_REQUIRED"


def test_criteria_weights_must_sum_to_100() -> None:
    db = MagicMock()
    opp = ProjectOpportunity(
        id=uuid.uuid4(),
        reference="OPP-2026-0003",
        title="KYC Ops",
        category="banking_kyc",
        status=OpportunityStatus.PUBLISHED,
        created_by=uuid.uuid4(),
    )
    db.execute.return_value.scalar_one_or_none.return_value = opp
    staff = _staff_ctx(StaffRole.SOURCING_MANAGER)

    with pytest.raises(AppError) as exc:
        opp_service.set_criteria_matrix(
            db,
            staff,
            opp.id,
            CriteriaMatrixIn(
                criteria=[
                    CriterionIn(name="Technical", weight_percent=60),
                    CriterionIn(name="Cost", weight_percent=30),
                ]
            ),
        )
    assert exc.value.code == "INVALID_WEIGHTS_SUM"


def test_proposal_deadline_enforcement() -> None:
    opp = ProjectOpportunity(
        id=uuid.uuid4(),
        reference="OPP-2026-0004",
        title="Data Processing",
        category="data_entry",
        status=OpportunityStatus.PUBLISHED,
        submission_deadline=datetime.now(UTC) - timedelta(hours=1),
        created_by=uuid.uuid4(),
    )
    with pytest.raises(AppError) as exc:
        opp_service._ensure_deadline_open(opp)
    assert exc.value.code == "DEADLINE_PASSED"


def test_contract_signature_hash_and_terms_validation() -> None:
    h1 = deliv_service._sig_hash(uuid.uuid4(), uuid.uuid4(), "Alice", "2026-11-25T09:00:00Z")
    assert len(h1) == 64

    db = MagicMock()
    contract = MagicMock()
    contract.status = deliv_service.ContractStatus.SENT_FOR_SIGNATURE
    db.execute.return_value.scalar_one_or_none.return_value = contract
    partner = MagicMock()
    partner.organization_id = uuid.uuid4()
    partner.user.id = uuid.uuid4()

    with pytest.raises(AppError) as exc:
        deliv_service.partner_sign_contract(
            db,
            partner,
            uuid.uuid4(),
            ContractSignIn(signer_name="Alice", accepted_terms=False),
        )
    assert exc.value.code == "TERMS_NOT_ACCEPTED"
