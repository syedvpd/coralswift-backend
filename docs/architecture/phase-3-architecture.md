# Phase 3 Architecture - Admin Backend

PRD basis: s.14 (dashboard modules, roles), s.15B (lead fields: source, category, priority, owner, status, next follow-up; routing), s.23 Phase 3
("enquiry/lead management, assignment, follow-ups, partner database, roles, reporting and audit logs"), s.19 (restricted access to confidential M&A and financial documents).

Reused: staff authentication + MFA gating (Phase 2), `activities` audit table (immutable), storage `get`, Phase 2 reviewer API (application oversight, reviewer assignment, workflow controls), Phase 1 enquiry/contact/company tables.
New (migration 0008, additive): `enquiries.assigned_user_id`, `enquiries.next_follow_up_at`, table `enquiry_followups`. Module: `app/modules/admin` (service + router under `/api/v1/admin`).

## Role matrix
| Capability | super_administrator | business_development_manager | partner_reviewer |
|---|---|---|---|
| General / project / partner enquiries: list, detail, status, priority, assign, follow-ups, download | yes | yes | no (Phase 2 reviewer API only) |
| Strategic (M&A) enquiries | yes | **no (404)** | no |
| Financial data (turnover band, client references, registration no., financial statements) | yes | hidden | no |
| Partner database (organizations) | full | limited profile | no |
| Suspend / reactivate organization, staff users, audit log, applications CSV | yes | no | no |
| Enquiries CSV | all types | excludes strategic | no |
| Applications: assign reviewer, workflow transitions | yes (Phase 2 reviewer endpoints) | no | assigned only |

Decisions needing the business owner: whether BDMs handle strategic "partnership discussions" (default: restricted to super admin); whether Content Administrator is needed (role exists, no Phase 3 endpoints).

## Added later (same phase)
Content CMS (draft -> review -> super-administrator approval -> publish, versions, attachments; Content Administrator drafts and publishes), notification-template and system-settings management,
meeting requests, newsletter opt-in, privacy requests, profile change requests, KPIs, maintenance jobs. Details: `docs/api/phase-3-api-contract.md`.

## Not built
SLA timers / auto-routing / escalation and the claims register (PRD s.28, excluded by the user), CRM/calendar integrations and everything in Phase 4.
Enquiry `status` keeps the Phase 1 values (received, in_review, closed): the PRD does not define lead stages.
