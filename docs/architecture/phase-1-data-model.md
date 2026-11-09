# Phase 1 Data Model (migrations 0002, 0003)

```
companies 1--* contacts           (contacts.company_id nullable)
contacts  1--* enquiries          (enquiries.contact_id)    companies 1--* enquiries (nullable)
enquiries 1--0..1 project_enquiries | partner_applications | strategic_enquiries   (UNIQUE enquiry_id)
enquiries 1--* documents          (documents.owner_id, nullable until attached)
enquiries 1--* notifications      (SET NULL)
activities (record_type, record_id)  idempotency_keys (scope, client_hash, key)
```

- All PKs UUID; timestamps `timestamptz` (UTC); FKs `ON DELETE RESTRICT` (notifications: `SET NULL`).
- Enums are VARCHAR + named CHECK constraints (easy to extend by migration).
- `enquiries.reference_number` UNIQUE, from sequence `enquiry_reference_seq` -> `CS-ENQ-<year>-<6 digits>`; never reused, gaps possible.
- Companies/contacts are **never merged** automatically; each submission creates its own rows.
- Contact CHECKs: lowercase email, E.164 phone, ISO-2 country. `consent_*` columns store grant, time and notice version.
- `partner_applications`: banded `workforce_range` / `turnover_range` are recorded only; CHECK: >=1 service category, >=2 client references. Statuses `submitted` (and reserved `under_review`); nothing approves or rejects.
- `strategic_enquiries.access_classification` defaults `confidential`; confidential text exists only here (`enquiries.message` is NULL).
- `documents`: metadata only (name, detected type, size, SHA-256, classification, `upload_status`, `retention_date` nullable). Bytes live in private storage under a server-generated `storage_key`. CHECK ties `owner_type`/`owner_id`.
- `notifications`: email outbox; `dedupe_key` UNIQUE (enquiry+template+recipient); `context` holds template variables only.
- `activities`: append-only; `metadata` must not contain PII/confidential text.
- `idempotency_keys`: UNIQUE(scope, client_hash, key); stores request hash and the original response; `expires_at` index for cleanup (`purge_expired`).

Migration safety: 0002/0003 are additive. Downgrade drops only objects they created. Apply with `alembic upgrade head`; never edit applied revisions.
