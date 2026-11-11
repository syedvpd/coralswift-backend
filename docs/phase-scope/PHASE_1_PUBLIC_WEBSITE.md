# PRD Phase 1 - Public Website (backend)

## Verification update (2026-11-11)

The full local suite passes (280 tests). Development migrations `0013`-`0015` are applied at Alembic head `0015`; see the audit and migration plan for evidence. Remaining Phase 1 gates are unresolved business inputs and external hosting/provider setup. Corporate/legal details and provider hostnames were not invented.

Date 2026-11-10. Evidence: commit `15ebe59` (254 tests passed locally). Uncommitted work from another agent is present in the working tree and is **not verified** here. Item-level detail: `DEVELOPER_REQUEST_TO_PRD_MAPPING.md`, `../backend-gap-audit.md`.

## Delivered and tested
- Five enquiry paths with typed schemas, server validation, unique reference, routing, acknowledgement, idempotency, rate limit and bot check: general contact, project, partner/vendor application, strategic, meeting request (`tests/api/test_contact.py`, `test_project_partner_strategic.py`, `test_idempotency.py`).
- Private, validated uploads kept `quarantined`; limits at `GET /admin/security-policy`; no public file URLs (`test_documents_status_security.py`).
- Public content delivery: published pages, articles, FAQs, resources with search, tags, related items, downloads, sitemap; drafts never exposed (`test_content_engagement.py`).
- Status lookup by token, newsletter opt-in, privacy-request intake, root redirect to docs in development.
- CORS code and preflight tests; Turnstile verifier (mock-tested); `X-Bot-Token` header.

## Remaining in-scope work
1. Privacy requests: add email confirmation to `POST /privacy/requests` (needs one token table, next migration number after `0012`).
2. Confirm with the PRD whether vendor/subcontracting needs its own route or classification (today: `pathway` field on the partner enquiry).
3. SEO fields (title, description, canonical, Open Graph) and media references on public content.
4. Homepage/hero/banners/services/industries/navigation delivery APIs, after decision D23.

## Blocked
Decisions: D23 (content model), D3 (queue owners/contact), D4 (privacy). External: frontend origin for CORS, Turnstile hostnames, Brevo domain authentication, HTTPS/CSP on the frontend host.

## Acceptance
Not yet met end to end: needs the remaining items above plus a live check of Turnstile and email. Phase 1 acceptance stays "not accepted" until the owner signs it off.

## Update 2026-11-10 (Claude Code)
Delivered: privacy-request email verification (`POST /privacy/requests/verify`, 72 h single-use link, `link` scrubbed from the outbox after sending); SEO/Open Graph and cover-image fields on content (https only). Tests: `tests/api/test_phase1_seo_privacy.py` (4, passed). Still open: media library, homepage/hero/banners/navigation (D23), vendor-path confirmation, live Turnstile/email checks.

## Completion (actual counts, 2026-11-10)
Local work only (no commit, push, deploy, backup or remote database operation). Full table with every requirement, evidence and tests: `REQUIREMENT_AUDIT_PHASES_1_3.md`. In scope 35 rows: **27 implemented and tested (77.1%)**, 2 implemented but not fully verified, 3 business-decision blocked (D23 page structure, D4 legal text, D3 owner/SLA values), 3 external (media hosting, email domain, CORS/HTTPS values). Not 100%: blocked rows remain. Out of scope/N-A: calendar integration, analytics (client-side), malware scanning (owner declined).
