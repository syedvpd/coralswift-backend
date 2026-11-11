# PRD Phase 3 - Admin Platform (backend)

## Verification update (2026-11-11)

The full local suite passes (280 tests). Development migrations `0013`-`0015` are applied at Alembic head `0015`. Workload covers enquiry counts only. Owner decisions and external configuration remain listed in the registers; live staff account/MFA verification was not performed.

Date 2026-11-10. Evidence: commit `15ebe59` (254 tests passed locally). Uncommitted work from another agent is present in the working tree and is **not verified** here. Item-level detail: `DEVELOPER_REQUEST_TO_PRD_MAPPING.md`, `../backend-gap-audit.md`.

## Delivered and tested
- Four roles, backend-enforced permissions, `GET /auth/permissions` derived from route guards, self-change protection (`test_gap_phase_a`, `test_gap_accounts`).
- Enquiries/leads: filters (category, IT/Non-IT, owner, dates), sort, assignment, activity feed, follow-up kinds, global follow-ups with counts (`test_gap_enquiries`).
- Strategic/M&A confidentiality on every path, including aggregates and exports (`test_strategic_confidentiality`).
- Applications: filters, contact, transitions table, clear reviewer (`test_gap_applications`); six PRD stages map 1:1 to statuses.
- Accounts and invitations: list, detail, resend, revoke, suspend, reactivate, admin-sent reset, rate limit.
- Document queue, typed settings, launch readiness, security policy, outbox, audit (names, `is_strategic`, search, sort), CSV exports with cap.
- Content workflow (draft, review, approval, publish, unpublish, versions, claims gate); privacy requests; KPIs including `portal_adoption`.

## Remaining in-scope work
1. Typed `/admin/overview`, `/admin/reports/kpis`, `/admin/organizations/{id}`, enquiry detail objects.
2. `discussion_type` filter; workload counts; organisation activity history; change-request before/after view.
3. Staff document review history; enquiry attachment list; admin notification feed; template placeholder list.
4. Audit get-by-id, event catalogue, export; report extensions (turnaround, partner-account metrics); staff profile update.
5. CMS media and SEO administration; scheduled publication only if approved (an uncommitted `0012` migration exists, unverified).

## Blocked
D3, D4, D5, D6, D7, D8, D9, D10, D11, D12 (confirm default), D15, D17, D18, D19, D20, D23, D24. External: Brevo delivery evidence, live role accounts, monitoring, backups.

## Acceptance
Core staff operations work through real APIs with tested permissions. Not complete until the items above and the decision-dependent features are done or formally blocked.

## Update 2026-11-10 (Claude Code)
Delivered and tested: staff notification feed (`/admin/feed`, `test_phase3_feed.py`, 2 passed). Fixed the earlier agent's failing report endpoint and 6 stale tests. Earlier-agent items present but not re-reviewed by me: typed overview/KPI/org/enquiry detail, workload, audit detail/export/catalogue, enquiry attachment list, document history, template placeholders, scheduled publication (`0012`, applied to Supabase dev).

## Completion (actual counts, 2026-11-10)
Local work only (no commit, push, deploy, backup or remote database operation). Full table with every requirement, evidence and tests: `REQUIREMENT_AUDIT_PHASES_1_3.md`. In scope 52 rows: **32 implemented and tested (61.5%)**, 8 implemented but not independently reviewed (earlier agent's typed overview/KPIs, workload, audit detail/export, document history, templates placeholders, reports, org detail, strategic filter), 10 business-decision blocked, 2 external. Added this session: `GET /admin/organizations/{id}/revisions` and `/activity` (strategic events excluded), `before` values and `organization_name` on pending profile change requests.
