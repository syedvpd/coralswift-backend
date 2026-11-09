# Phase 2 Data Model (migrations 0004-0007, additive)

Conventions as Phase 1: UUID PKs, `timestamptz` UTC, enums = VARCHAR + named CHECK, FKs `RESTRICT`. Sensitivity: **S3** secrets/credentials (hashed only),
**S2** confidential business / personal data, **S1** internal operational, **S0** low.

| Table | Purpose | Key columns / constraints | Sens. |
|---|---|---|---|
| `users` | Partner and staff accounts | `email` UNIQUE lowercase; `password_hash` (Argon2id, null until activation); `user_type` partner/staff; `staff_role` (required iff staff); `status` invited/active/deactivated; `failed_login_count`, `locked_until`, `last_login_at` | S3/S2 |
| `auth_tokens` | One-time invitation / reset tokens | `token_hash` UNIQUE (SHA-256); `purpose`; `user_id` or `email`; `organization_id`; `expires_at`; `used_at` | S3 |
| `auth_sessions` | Login sessions | `access_hash` UNIQUE, `refresh_hash` UNIQUE, `prev_refresh_hash`; expiries; `revoked_at`; `ip_hash`, `user_agent` (truncated) | S3 |
| `partner_organizations` | Partner company + profile | `legal_name`, `status`, profile fields (registration no., year established, employee count, annual turnover INR crore, address, country, website, services, capabilities, infrastructure, references JSONB, description, authorised contacts JSONB); `source_enquiry_id` -> Phase 1 `enquiries` (nullable, link only); `version` counter | S2 |
| `partner_memberships` | User belongs to organization | UNIQUE(org,user); partial UNIQUE(user) where active (one active org per user); `role` owner/member; `status` | S1 |
| `partner_profile_revisions` | Profile change history | org, `version`, `changed_by`, `changes` JSONB `{field:{old,new}}`, created_at; append-only | S2 |
| `partner_documents` | Logical document (per org + category) | `organization_id`, `category`, `status` active/removed, `current_version_no` | S2 |
| `partner_document_versions` | Immutable file versions | UNIQUE(document,version_no); `storage_key` UNIQUE (server-generated); type, size, SHA-256; `upload_status`; `expires_on`; `review_status` pending/accepted/rejected/clarification_needed; `review_comment`; reviewer; `retention_date` | S2 |
| `portal_applications` | Application lifecycle | `reference` UNIQUE (`CS-APP-YYYY-NNNNNN`, sequence `portal_application_seq`); `organization_id`; `pathway`; `status`; `resume_status`; `assigned_reviewer_id`; `submitted_at`, `decided_at`; partial UNIQUE(org) where status not terminal; `version` | S2 |
| `application_submissions` | Immutable snapshot per (re)submission | UNIQUE(application, submission_no); `snapshot` JSONB (profile + document version ids); submitted_by | S2 |
| `application_status_history` | Every transition | from/to, actor, `reason` (reviewer-only), `partner_note` (partner-visible), created_at | S1 |
| `eligibility_verifications` | Human verification records (append-only) | application, submission_no, verified values, `outcome`, `exception_note`, `notes`, `supporting_version_ids`, reviewer | S2 |
| `reviewer_notes` | Internal notes (never exposed to partners) | application, author, body | S2 |
| `application_messages` | Partner-visible conversation | `kind` information_request/partner_response; `status` open/answered; `in_reply_to_id`; `requested_categories`; author | S2 |
| `activities` (Phase 1, extended) | Audit trail | + `actor_user_id`, `organization_id`, `request_id`; CHECK widened for actor types; trigger blocks UPDATE/DELETE | S1 |
| `notifications` (Phase 1, extended) | Outbox | CHECK widened for new template keys / types | S2 |

## Relationships
```
users 1--0..1 partner_memberships *--1 partner_organizations 1--* partner_documents 1--* partner_document_versions
partner_organizations 1--* portal_applications 1--* application_submissions / application_status_history / eligibility_verifications
                                              1--* reviewer_notes / application_messages ;  portal_applications *--0..1 users (assigned reviewer)
partner_organizations 1--* partner_profile_revisions ; partner_organizations *--0..1 enquiries (Phase 1 source)
```

## Isolation strategy
Every partner-facing query joins/filters on `organization_id` taken from the authenticated membership, never from request input. Cross-organization ids
return 404. Reviewer queries filter `assigned_reviewer_id = current user`. No list endpoint is unscoped. Internal notes and `reason` columns are excluded
from partner response schemas by construction (separate schema classes).

## Retention
Soft delete only; `retention_date` stays null until a policy is approved (open decision). Audit rows are immutable at database level.

## Migration plan (as built: 0004 foundation, 0005 documents, 0006 applications; applied locally and, on user instruction, to the Supabase dev DB)
0004 users, auth_tokens, auth_sessions, activities extension + immutability trigger, notification CHECK widening.
0005 partner_organizations, partner_memberships, partner_profile_revisions.
0006 partner_documents, partner_document_versions.
0007 portal_applications (+sequence), submissions, status history, eligibility, notes, messages.
