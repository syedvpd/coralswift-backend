# Phase 1 API Contracts

Base `/api/v1`. Success envelope `{success, message, data, meta}`; error envelope `{success:false, message, error:{code, details[]}}`. Swagger: `/docs` (non-production).

Common submitter block (all four forms): `full_name`, `designation?`, `business_email`, `phone` (international, normalised to `+digits`), `country` (ISO-2), `company_name?`, `privacy_consent` (must be `true`). Unknown fields are rejected (422).
Optional headers: `Idempotency-Key` (8-128 chars), `X-Bot-Token` (CAPTCHA hook, unused until a provider is chosen).

| Method & path | Purpose | Extra fields |
|---|---|---|
| `POST /enquiries/contact` | General enquiry | `enquiry_type` (general_information, services, partnership, other), `message` (5-5000) |
| `POST /enquiries/project` | Project enquiry (categories only, not live projects) | `company_name`, `project_category`, `requirement_summary`, `scope`, `expected_timeline`, `estimated_volume?`, `geography`, `security_constraints?`, `document_ids[]` |
| `POST /enquiries/partner` | Partner application (recorded for human review) | `designation`, `website?`, `year_established`, `registered_address`, `company_country`, `preferred_engagement_pathway`, `workforce_range`, `turnover_range`, `service_categories[]`, `infrastructure_summary`, `client_experience`, `client_references[2..5]`, `document_ids[]` |
| `POST /enquiries/strategic` | Confidential strategic/merger/integration enquiry | `company_name`, `designation`, `discussion_type`, `business_overview`, `confidential_summary`, `authorized_representative` (true), `document_ids[]` |
| `POST /documents/upload` (multipart) | Upload supporting file | `file`, `purpose` (project_attachment, partner_evidence, strategic_attachment), `category` (required only for partner_evidence) |
| `GET /enquiries/{reference}/status` | Public status | header `X-Lookup-Token` |

Submission response (201):
```json
{"success":true,"message":"Submission received","data":{"reference_number":"CS-ENQ-2026-000042","lookup_token":"<40 hex>","enquiry_type":"general","status":"received","submitted_at":"2026-11-09T10:00:00Z","documents_attached":0},"meta":null}
```
Replay of the same `Idempotency-Key` + body returns the same body with header `Idempotent-Replay: true`.

Upload response (201): `document_id`, `original_filename`, `content_type`, `file_size`, `checksum_sha256`, `upload_status` (`quarantined`). Storage keys are never returned. Pass `document_id` in `document_ids` of the matching form (purpose must match the form).

Status response (200): `reference_number`, `enquiry_type`, `status`, `submitted_at`. Wrong token, missing token, unknown or malformed reference all give the same 404.

Error codes: `VALIDATION_ERROR` 422, `INVALID_DOCUMENT_REFERENCE` 422, `IDEMPOTENCY_KEY_REUSED` 422, `INVALID_IDEMPOTENCY_KEY` 422, `REQUEST_IN_PROGRESS` 409, `UNSUPPORTED_FILE_TYPE` 415, `FILE_TOO_LARGE` 413, `PAYLOAD_TOO_LARGE` 413, `TOO_MANY_REQUESTS` 429 (+`Retry-After`), `BOT_CHECK_FAILED` 403, `STORAGE_UNAVAILABLE` 503.

## Behaviour notes
- **Lookup token** = HMAC-SHA256(SECRET_KEY, reference), truncated to 40 hex. Not stored. Rotating `SECRET_KEY` invalidates issued tokens.
- **Idempotency**: claim row is committed first (unique constraint picks one winner); the response is stored in the same transaction as the enquiry; failed attempts release the key; keys expire after `IDEMPOTENCY_TTL_HOURS` (default 24); a claim stuck "in progress" >60 s is treated as crashed. Without a key, identical resubmissions create separate enquiries (no content-based merging).
- **Rate limiting**: in-process fixed window per client IP (`RATE_LIMIT_PER_MINUTE`, uploads x2, status x3). Per worker only; enforce at proxy/CDN in production.
- **Uploads**: extension allow-list (pdf, png, jpg/jpeg, docx, xlsx) + magic-byte check + declared-type consistency; max `MAX_UPLOAD_BYTES`; server-generated key `enquiries|partners/YYYY/MM/<uuid>.<ext>`; SHA-256; stored privately; status `quarantined` because **no malware scanner is configured**. No download endpoint exists.
- **Storage**: `STORAGE_BACKEND=local` (dev, `STORAGE_LOCAL_ROOT`) or `s3` (S3-compatible; partner evidence goes to `S3_PARTNER_BUCKET` when set).
- **Email**: outbox rows are written in the enquiry transaction; sending runs after commit (background task). `EMAIL_BACKEND=console` logs only and records status `logged` (never `sent`); `brevo` calls the Brevo API with `BREVO_API_KEY`. Failed sends are retried by re-running dispatch (cap `NOTIFICATION_MAX_RETRIES`). Internal mail goes to `NOTIFY_<QUEUE>_EMAILS`; strategic internal mail carries no submitter or confidential details. Templates promise no response time.
- **Privacy**: consent timestamp + notice version stored; `PRIVACY_NOTICE_VERSION` is `draft-unapproved` until legal approves the notice.
