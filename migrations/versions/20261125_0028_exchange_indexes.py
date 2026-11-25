"""add indexes for project exchange foreign keys and statuses

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-25 09:42:00
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

INDEXES = [
    ("ix_evaluation_criteria_opportunity_id", "evaluation_criteria", ["opportunity_id"]),
    ("ix_milestone_comments_milestone_id", "milestone_comments", ["milestone_id"]),
    ("ix_milestone_deliverables_milestone_id", "milestone_deliverables", ["milestone_id"]),
    ("ix_milestone_deliverables_organization_id", "milestone_deliverables", ["organization_id"]),
    ("ix_milestone_deliverables_status", "milestone_deliverables", ["status"]),
    ("ix_opportunity_brief_accesses_opportunity_id", "opportunity_brief_accesses", ["opportunity_id"]),
    ("ix_opportunity_brief_accesses_organization_id", "opportunity_brief_accesses", ["organization_id"]),
    ("ix_opportunity_invitations_opportunity_id", "opportunity_invitations", ["opportunity_id"]),
    ("ix_opportunity_invitations_organization_id", "opportunity_invitations", ["organization_id"]),
    ("ix_opportunity_questions_opportunity_id", "opportunity_questions", ["opportunity_id"]),
    ("ix_opportunity_questions_organization_id", "opportunity_questions", ["organization_id"]),
    ("ix_project_closures_organization_id", "project_closures", ["organization_id"]),
    ("ix_project_contracts_opportunity_id", "project_contracts", ["opportunity_id"]),
    ("ix_project_contracts_organization_id", "project_contracts", ["organization_id"]),
    ("ix_project_contracts_project_id", "project_contracts", ["project_id"]),
    ("ix_project_contracts_proposal_id", "project_contracts", ["proposal_id"]),
    ("ix_project_contracts_status", "project_contracts", ["status"]),
    ("ix_project_invoices_organization_id", "project_invoices", ["organization_id"]),
    ("ix_project_invoices_project_id", "project_invoices", ["project_id"]),
    ("ix_project_invoices_status", "project_invoices", ["status"]),
    ("ix_project_proposals_opportunity_id", "project_proposals", ["opportunity_id"]),
    ("ix_project_proposals_organization_id", "project_proposals", ["organization_id"]),
    ("ix_project_proposals_status", "project_proposals", ["status"]),
    ("ix_proposal_scores_criterion_id", "proposal_scores", ["criterion_id"]),
    ("ix_proposal_scores_proposal_id", "proposal_scores", ["proposal_id"]),
]


def upgrade() -> None:
    for name, table, cols in INDEXES:
        op.create_index(op.f(name), table, cols)


def downgrade() -> None:
    for name, table, _ in reversed(INDEXES):
        op.drop_index(op.f(name), table_name=table)
