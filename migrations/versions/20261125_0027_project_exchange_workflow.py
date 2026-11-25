"""project exchange workflow: opportunities, proposals, scoring, contracts, deliverables, closure, invoices, compliance, new staff roles

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-25 09:30:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

OLD_ROLES = "'partner_reviewer','super_administrator','business_development_manager','content_administrator'"
NEW_ROLES = (
    OLD_ROLES
    + ",'sourcing_manager','compliance_officer','delivery_manager','finance','auditor','approver'"
)


def upgrade() -> None:
    op.drop_constraint(op.f("ck_users_staff_role"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_staff_role"), "users", f"staff_role IN ({NEW_ROLES})"
    )

    op.create_table(
        "project_opportunities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("required_skills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("budget_min", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("budget_max", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("expected_timeline", sa.String(length=150), nullable=True),
        sa.Column("geography", sa.String(length=150), nullable=True),
        sa.Column("compliance_requirements", sa.Text(), nullable=True),
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
        sa.Column("submission_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("structured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sourcing_manager_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("visibility", sa.String(length=40), nullable=True),
        sa.Column("target_categories", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("shortlisted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shortlisted_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("shortlist_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("shortlist_approved_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("shortlist_decision_notes", sa.Text(), nullable=True),
        sa.Column("awarded_proposal_id", sa.Uuid(), nullable=True),
        sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_opportunities")),
        sa.UniqueConstraint("reference", name=op.f("uq_project_opportunities_reference")),
    )
    op.create_index(op.f("ix_project_opportunities_category"), "project_opportunities", ["category"])
    op.create_index(op.f("ix_project_opportunities_status"), "project_opportunities", ["status"])

    op.create_table(
        "opportunity_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("project_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("partner_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invited_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_invitations")),
        sa.UniqueConstraint("opportunity_id", "organization_id", name="uq_opp_invite"),
    )

    op.create_table(
        "opportunity_brief_accesses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("project_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("partner_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_brief_accesses")),
    )

    op.create_table(
        "opportunity_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("project_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("partner_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("asked_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_questions")),
    )

    op.create_table(
        "project_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("project_opportunities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("partner_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("technical_approach", sa.Text(), nullable=True),
        sa.Column("proposed_timeline", sa.String(length=150), nullable=True),
        sa.Column("proposed_budget", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("team_summary", sa.Text(), nullable=True),
        sa.Column("deliverables_plan", sa.Text(), nullable=True),
        sa.Column("document_ids", postgresql.ARRAY(sa.Uuid()), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weighted_score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("is_shortlisted", sa.Boolean(), nullable=False),
        sa.Column("shortlist_rank", sa.Integer(), nullable=True),
        sa.Column("shortlist_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_proposals")),
        sa.UniqueConstraint("reference", name=op.f("uq_project_proposals_reference")),
        sa.UniqueConstraint("opportunity_id", "organization_id", name="uq_opp_org_proposal"),
    )

    op.create_table(
        "evaluation_criteria",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("project_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight_percent", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("weight_percent BETWEEN 1 AND 100", name="weight_range"),
        sa.CheckConstraint("max_score > 0", name="max_score_positive"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_criteria")),
    )

    op.create_table(
        "proposal_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), sa.ForeignKey("project_proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("criterion_id", sa.Uuid(), sa.ForeignKey("evaluation_criteria.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scorer_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("score", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposal_scores")),
        sa.UniqueConstraint("proposal_id", "criterion_id", name="uq_proposal_criterion_score"),
    )

    op.create_table(
        "project_contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), sa.ForeignKey("project_opportunities.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("proposal_id", sa.Uuid(), sa.ForeignKey("project_proposals.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("partner_projects.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("partner_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("scope_summary", sa.Text(), nullable=True),
        sa.Column("contract_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("partner_documents.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("partner_signed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("partner_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("partner_signature_hash", sa.String(length=128), nullable=True),
        sa.Column("staff_countersigned_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("staff_countersigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staff_signature_hash", sa.String(length=128), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_contracts")),
        sa.UniqueConstraint("reference", name=op.f("uq_project_contracts_reference")),
    )

    op.create_table(
        "milestone_deliverables",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), sa.ForeignKey("project_milestones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("partner_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
        sa.Column("document_ids", postgresql.ARRAY(sa.Uuid()), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestone_deliverables")),
    )

    op.create_table(
        "milestone_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), sa.ForeignKey("project_milestones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("author_type", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_milestone_comments")),
    )

    op.create_table(
        "project_closures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("partner_projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("partner_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("outcomes", sa.Text(), nullable=True),
        sa.Column("lessons_learned", sa.Text(), nullable=True),
        sa.Column("partner_rating", sa.Integer(), nullable=False),
        sa.Column("delivery_quality_score", sa.Integer(), nullable=True),
        sa.Column("timeliness_score", sa.Integer(), nullable=True),
        sa.Column("communication_score", sa.Integer(), nullable=True),
        sa.Column("closed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("partner_rating BETWEEN 1 AND 5", name="partner_rating_range"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_closures")),
        sa.UniqueConstraint("project_id", name=op.f("uq_project_closures_project_id")),
    )

    op.create_table(
        "project_invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("invoice_number", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("partner_projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_id", sa.Uuid(), sa.ForeignKey("project_contracts.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("milestone_id", sa.Uuid(), sa.ForeignKey("project_milestones.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("partner_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("partner_documents.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_reference", sa.String(length=100), nullable=True),
        sa.Column("finance_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_invoices")),
        sa.UniqueConstraint("invoice_number", name=op.f("uq_project_invoices_invoice_number")),
    )

    op.create_table(
        "partner_compliance_screenings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("partner_organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kyc_status", sa.String(length=40), nullable=False),
        sa.Column("kyb_status", sa.String(length=40), nullable=False),
        sa.Column("sanctions_status", sa.String(length=40), nullable=False),
        sa.Column("screening_notes", sa.Text(), nullable=True),
        sa.Column("screened_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("screened_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partner_compliance_screenings")),
        sa.UniqueConstraint("organization_id", name=op.f("uq_partner_compliance_screenings_organization_id")),
    )


def downgrade() -> None:
    op.drop_table("partner_compliance_screenings")
    op.drop_table("project_invoices")
    op.drop_table("project_closures")
    op.drop_table("milestone_comments")
    op.drop_table("milestone_deliverables")
    op.drop_table("project_contracts")
    op.drop_table("proposal_scores")
    op.drop_table("evaluation_criteria")
    op.drop_table("project_proposals")
    op.drop_table("opportunity_questions")
    op.drop_table("opportunity_brief_accesses")
    op.drop_table("opportunity_invitations")
    op.drop_index(op.f("ix_project_opportunities_status"), table_name="project_opportunities")
    op.drop_index(op.f("ix_project_opportunities_category"), table_name="project_opportunities")
    op.drop_table("project_opportunities")

    op.drop_constraint(op.f("ck_users_staff_role"), "users", type_="check")
    op.create_check_constraint(
        op.f("ck_users_staff_role"), "users", f"staff_role IN ({OLD_ROLES})"
    )
