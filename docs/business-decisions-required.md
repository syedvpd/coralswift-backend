# Business Decisions Required (2026-11-10)

Unresolved decisions only. Each blocks the audit items named. "Recommended" is a suggestion, not a decision. Earlier decision register with queue/SLA/contact items: `docs/requirements/business-decision-register.md` (D3-D4 here extend it).
Decided already: quarantine-only uploads accepted, no malware scanner (owner, 2026-11-10).

| Id | Decision needed | Impact / blocked items | Recommended | Owner input |
|---|---|---|---|---|
| D1 | Session persistence: keep tokens in the response body, or add an HttpOnly cookie session (needs a same-site domain, CSRF protection) | X10, P1.4: reload signs the user out | Keep bearer tokens; frontend stores the refresh token in memory plus a short-lived secure store; revisit cookies once there is a custom domain | Owner + frontend lead |
| D2 | Should login reveal "account not activated" or "already has an account"? | P1.5, P14.7: reveals which emails exist | Keep generic. Already explicit only for a deactivated account with the right password | Owner / security |
| D3 | Queue owners, backup owners, SLA hours, escalation recipients per queue; contact details | launch gate, P9.7, routing | Named people per queue incl. a strategic owner; start with 24-48 h first response | Business owner |
| D4 | Retention periods, deletion policy, privacy-request procedure, legal-retention checks before irreversible deletion | X13, M12, P20.6 | Set `retention.partner_document_days` after legal sign-off; require a written check before `execute` | Owner + legal |
| D5 | Eligibility exceptions: who may approve, what is recorded | M7, P6.6 | Super administrator approves with a written reason; stored as an exception record per application | Business owner |
| D6 | Thresholds (3 years, 50 personnel, INR 2 crore) per pathway; mandatory documents per pathway | M9, P6.6, P7.4 | Confirm per pathway in a table; then expose through the criteria endpoint | Business owner |
| D7 | Explicit "approved" status | P4.1, P6.4 | Keep `pilot_onboarding` as the approval point and label it "Approved - pilot" in the UI | Business owner |
| D8 | Enquiry status workflow: allowed transitions, extra statuses (awaiting response, completed, active discussion, awaiting decision) | X5 (enquiries), P8.6, P9.4 | Add `awaiting_response` and `completed`; allow only forward moves plus reopen | Business owner |
| D9 | Review checklist items, scoring (PRD forbids automated final decisions), a separate "recommend" step | P6.1, P6.2 | Reviewer checklist as recorded yes/no items with notes, no scores | Business owner |
| D10 | Onboarding model: stages, tasks, due dates, completion rules | P4.3, P7.1, P25.3, P27.3, P29.1 | Task list per application created at `pilot_onboarding`, with due dates | Business owner |
| D11 | Reversal / reconsideration of a rejected or withdrawn application | P6.3 | Allow a super administrator to reopen with a recorded reason | Business owner |
| D12 | May Business Development Managers see strategic/M&A enquiries? | P9.1 | No (current behaviour) | Owner |
| D13 | Workload and capacity rules for assignment | P10.2 | Show open counts per assignee; no hard caps | Business owner |
| D14 | Assignment workflow for partner and meeting enquiries | P10.7 | Use the existing owner field and routing settings | Business owner |
| D15 | Sending ad-hoc / external messages to requesters from the console | P11.4, P15.2 | Later, via the transactional provider with approved templates only | Owner |
| D16 | Calendar provider (or accept staff-attested meeting confirmation) | P11.6, M11 | Accept staff-attested confirmation until a provider is chosen | Owner |
| D17 | Should staff upload, replace or delete partner documents? | P12.3 | No; ask the partner for a new version | Business owner |
| D18 | A separate "replacement requested" document status | P12.6 | Keep `clarification_needed` | Business owner |
| D19 | Direct staff edit of a partner profile | P13.1 | No; keep partner edits and change-request approval | Business owner |
| D20 | Extra profile fields (trading name, type, region, industry, competencies, etc.) | P13.2, P26.1 | Add only those the review needs, as nullable fields | Business owner |
| D21 | Agreements and relationship-manager fields | P13.4 | Out of scope until a CRM decision | Owner |
| D22 | Partner role-specific permissions beyond owner/member | P14.4 | Keep two roles | Business owner |
| D23 | CMS content model: homepage/hero/banners/menus, rich text, media | P16.1, P16.6 | Define page types first; keep plain text until then | Business owner + frontend |
| D24 | Who approves content (super administrator only today) | P16.7 | Keep; add a content-approver role only if staffing needs it | Business owner |
| D25 | Editing role permissions at runtime | P17.3 | No; four fixed roles | Owner |
| D26 | PDF / Excel exports | P18.6 | CSV only | Business owner |
| D27 | Should partners see the eligibility outcome and reviewer reasons? | P28.1 | Show decision and a reviewer-written partner note only | Business owner |

External configuration (not decisions): Brevo key, verified sender domain and SPF/DKIM/DMARC; Turnstile keys; a domain and hostnames; CORS origin value on Render; staging database and buckets; credential rotation; monitoring and backups. See `production-readiness-report.md`.
