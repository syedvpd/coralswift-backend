# Backend Service Layer & PostgreSQL Database Audit

**Database:** PostgreSQL 16+ via SQLAlchemy 2.0 (ORM + Core) & Alembic  
**Driver:** `psycopg` (binary, version 3.3.8)  
**Migration Head:** `0025_review_workflow_and_team.py`

---

## 1. Database Architecture & Model Mapping

The database schema is organized into modular tables with foreign keys and strict constraints:

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│           enquiries             │       │      portal_applications        │
├─────────────────────────────────┤       ├─────────────────────────────────┤
│ id (PK, UUID)                   │       │ id (PK, UUID)                   │
│ reference_number (UK, VARCHAR)  │       │ reference (UK, VARCHAR)         │
│ enquiry_type (VARCHAR)          │       │ organization_id (FK -> orgs.id) │
│ full_name, email, phone         │       │ status (VARCHAR, 10 states)     │
│ payload (JSONB)                 │       │ pathway (VARCHAR, 3 enums)      │
│ assigned_to_user_id (FK)        │       │ assigned_reviewer_id (FK)       │
│ status (VARCHAR)                │       │ submitted_at, decided_at        │
│ created_at, updated_at          │       │ ⚠️ NO assigned_bdm_id           │
│ ⚠️ NO FK to portal_applications │       │ ⚠️ NO FK to enquiries.id        │
└─────────────────────────────────┘       └─────────────────────────────────┘
                 ▲                                         ▲
                 │                                         │
        Public Intake Web Form                     Partner Portal Queue
                 │                                         │
                 └─────────────── [GAP] ───────────────────┘
                    No Automatic Ingestion Bridge!
```

---

## 2. Table-by-Table Audit

### A. Intake & Enquiries
- **`enquiries`**: Primary table for public website form submissions (`contact`, `partner`, `project`, `strategic`).
  - Columns: `id`, `reference_number`, `enquiry_type`, `full_name`, `business_email`, `phone`, `country`, `company_name`, `message`, `consent_version`, `status`, `assigned_to_user_id`, `created_at`.
  - Relationships: Has many `enquiry_attachments`, logs to `activities`.
  - **Audit Finding:** Submissions to `POST /api/v1/enquiries/partner` write exclusively here. There is no DB foreign key or trigger creating a `portal_applications` row.

### B. Organizations & Partner Portal
- **`partner_organizations`**: Companies registered on the platform.
  - Columns: `id`, `legal_name`, `trading_name`, `company_type`, `incorporation_date`, `tax_id`, `website`, `address_line1`, `city`, `state`, `country`, `workforce_size`, `annual_turnover`, `competencies` (ARRAY), `source_enquiry_id` (FK to `enquiries.id`), `created_at`.
  - **Audit Finding:** `source_enquiry_id` exists on `partner_organizations`, which proves the design intended to connect enquiries to organizations, but currently it is only populated when a Super Admin manually invites a partner via `POST /reviewer/invitations`.
- **`partner_memberships`**: Maps `users` to `partner_organizations`.
  - Roles: `owner`, `member`.
  - Status: `active`, `invited`, `deactivated`.

### C. Partner Applications & Review
- **`portal_applications`**: Applications in the 6-stage review pipeline.
  - Columns: `id`, `reference`, `organization_id` (FK), `pathway`, `status`, `assigned_reviewer_id` (FK), `snapshot` (JSONB), `submission_count`, `submitted_at`, `decided_at`, `decision_reason`.
  - **Audit Finding:**
    1. **Missing `assigned_bdm_id`:** Only one staff member (`assigned_reviewer_id`) can be assigned. Dual assignment (BDM + Reviewer) is structurally impossible in the current schema.
    2. **Missing `enquiry_id`:** No link back to the originating public enquiry record.
- **`application_status_history`**: Immutable status transition log with `from_status`, `to_status`, `actor_id`, `actor_role`, `reason`, `created_at`.
- **`application_review_notes`**: Internal confidential notes with `actor_id`, `note`, `created_at`.

### D. Missing Evaluation Domain Tables
- **`capability_reviews`**: **DOES NOT EXIST.** Currently capability assessment is stored as generic key-value items in `review_checklist_items`. There are no dedicated columns for `infrastructure_rating`, `domain_expertise_rating`, `team_strength_rating`, or `delivery_capability_rating`.
- **`commercial_legal_reviews`**: **DOES NOT EXIST.** No structured persistence for `nda_executed`, `ip_terms_accepted`, `pricing_terms`, or `legal_signoff`.
- **`application_recommendations`**: **DOES NOT EXIST.** Recommendations cannot be formally logged separate from status transitions.

---

## 3. Database Integrity & Constraints Verification

| Model / Table | Primary Key | Foreign Keys | Unique Constraints | Cascade Rules | Soft Delete | Status |
|---|---|---|---|---|---|---|
| `users` | UUID | None | `email` (lower) | N/A | Status flag | ✅ Verified |
| `partner_organizations` | UUID | `creator_id`, `source_enquiry_id` | `legal_name` | Restrict | Status flag | ✅ Verified |
| `partner_memberships` | UUID | `user_id`, `organization_id` | `(user_id, organization_id)` | Cascade | Status flag | ✅ Verified |
| `portal_applications` | UUID | `organization_id`, `reviewer_id` | `reference` | Restrict | Withdrawn state | ⚠️ Missing BDM FK |
| `application_documents` | UUID | `application_id`, `uploader_id` | `(application_id, category)` | Restrict | None | ✅ Verified |
| `review_checklist_items`| UUID | `application_id`, `actor_id` | `(application_id, stage, name)`| Cascade | None | ✅ Verified |
| `onboarding_records` | UUID | `organization_id`, `application_id` | `organization_id` | Restrict | None | ✅ Verified |
| `onboarding_tasks` | UUID | `record_id` | None | Cascade | None | ✅ Verified |
| `performance_entries` | UUID | `organization_id`, `recorded_by` | `(organization_id, period, key)`| Restrict | None | ✅ Verified |

---

## 4. Transaction Boundaries & Concurrency

- **Session Lifecycle:** Managed via FastAPI dependency `DbSession = Annotated[Session, Depends(get_db)]`. Transactions commit explicitly via `db.commit()` in service handlers.
- **Savepoints:** Test factory uses `join_transaction_mode="create_savepoint"`, guaranteeing zero test database pollution.
- **Optimistic Locking:** Enforced on `partner_organizations` and `portal_applications` via `updated_at` / version checks, preventing concurrent overwrite races.
- **Idempotency:** Implemented via `IdempotencyRecord` table with 24-hour TTL, caching payload hashes and responses for public form POST operations.

