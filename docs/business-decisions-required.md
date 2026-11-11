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

## Added 2026-11-10
| Id | Decision | Impact | Recommended |
|---|---|---|---|
| D28 | Confirm the partner MFA policy (required / optional / off) | MFA disable for partners follows today's "optional" behaviour | Optional, enforced once enabled |
| D29 | Public media hosting for website images (bucket/CDN) | Cover images are https URLs only; no upload library | Use a public CDN bucket separate from private documents |

## Frontend recommendations received (2026-11-11; not owner decisions)

The frontend handoff supplied recommendations for D1-D12, D15-D20, D22-D23, and D27-D29. They remain unapproved until the business owner confirms them. D1 proposes an HttpOnly/Secure/SameSite refresh cookie; D2 generic login errors; D3 a named super administrator and one-business-day first response; D4 legal-set retention periods and staff-reviewed deletion; D5 super-admin eligibility exceptions with reason and audit; D6 PRD thresholds as defaults and owner-supplied document categories; D7 keeps `pilot_onboarding` as approval; D8 adds statuses only if used operationally; D9 proposes pass/fail/not-applicable checklists without scoring; D10 defers onboarding stages/tasks; D11 proposes one audited super-admin reconsideration; D12 keeps strategic enquiries super-admin-only; D15/D16 defer ad-hoc email and calendar integration; D17-D20 retain the current document/profile policies and PRD fields; D22 keeps owner/member roles; D23 defers homepage/navigation/media structures; D27 proposes a reviewer-authored partner-safe reason; D28 keeps partner MFA optional; D29 defers a media library.

Owner input still required: named owners and response target (D3), retention/legal process (D4), exception authority (D5), thresholds and mandatory documents (D6), checklist items/approver flow (D9), onboarding stages/tasks (D10), and confirmation of each recommendation before it becomes policy. Without a decision, dependent behavior remains as currently implemented or deferred; no policy was guessed.

## Added 2026-11-11 (frontend requirements batch). Nothing below is applied until the owner approves it

| Id | Decision needed | Code / API affected | Recommended default (not applied) | Risk of the default |
|---|---|---|---|---|
| D30 | Approve functionality that PRD s.23 and `docs/phase-scope/PHASE_4_EXCLUSIONS.md` exclude: shared **projects** (`/partner/projects`), partner **discussions / meetings / follow-ups**, org-wide **inbox** with attachments and `partner_visible` admin messages, **notification preferences**, partner-run **team management** (invite/role/remove/ownership transfer), approved sender labels | New modules, new tables, new partner and admin endpoints; P2-01, P2-05d, P2-06, P2-07, P2-08 in the tracker | Approve in this order if at all: (1) org inbox, (2) team management limited to invite/resend/cancel/deactivate with last-owner protection, (3) projects. Keep calendar integration out (D16) | Each is a new data-sharing surface for partners (confidentiality, isolation tests, retention); roughly one migration and one test file per feature |
| D31 | Test environment provisioning: approve (a) the development database as the target, (b) emails or aliases for 4 staff, 2 partner, 1 invited-inactive account, (c) a secure channel for credentials | `scripts/create_staff_user.py`; P1-02 | Dedicated `+alias` mailboxes you control; credentials delivered through a password manager, never in chat or the repo | Seeding into the wrong database; no mailbox exists until Brevo is configured |
| D32 | Exact production/preview origins for the admin console and partner portal (public site origins are already recorded) | `CORS_ALLOWED_ORIGINS` on Render; P1-01 | One explicit origin per portal plus `http://localhost:5173` for dev only | A missing origin keeps preflight failing; wildcard origins are rejected in staging/production |
| D33 | Malware scanning: **re-opened by the frontend** after the owner accepted quarantine-only on 2026-11-10. Choose: keep quarantine-only, or approve a provider (ClamAV container, or a managed scanner) and whether download/review must wait for `clean` | `scan_status` (now returns `not_scanned`), document download/review routes, storage; P1-06 | Keep quarantine-only until a domain and hosting exist; then add ClamAV as a worker | A scanner means a new service to run and update; blocking downloads until clean needs a failure/timeout policy |
| D34 | Privacy-request SLA (days to respond/complete) and who completes them | `/admin/privacy-requests`, `due` logic, P1-11 | 30 days to complete, 72 h to verify email (verification TTL is already 72 h) | Legal minimums differ by jurisdiction |
| D35 | Providers: hosting, transactional email (Brevo is wired but has no key), calendar, CRM | `EMAIL_BACKEND`, `render*.yaml`, bounce webhooks (A-08b) | Keep Render + Supabase + Brevo; no calendar, no CRM | None until a domain exists |
| D36 | Audit detail: may the audit log store IP, user agent, outcome and before/after values (personal data)? Also: runtime write of the security policy, and secrets through an API | `Activity.meta`, `/admin/audit`, `/admin/security-policy`; A-12b, A-12c, A-13e | Store IP and user agent with a retention limit; before/after for non-personal fields only; keep secrets in environment variables and keep the policy read-only | Personal data in an append-only log conflicts with erasure requests (D4) |
| D37 | Login disclosure: (a) keep `ACCOUNT_LOCKED` (423, only shown with the correct password), (b) reveal "not activated" for invited accounts | `auth/service.py::login` | (a) keep (b) no | (a) none beyond a known-password holder learning the lock; (b) would let anyone learn which emails are invited |
| D38 | Activation link path: frontend assumes `/partner/activate?token=`, backend emails `/activate?token=` | invitation email template, `PORTAL_BASE_URL` | Change the frontend route to `/activate` (no backend change) | Staff and partner invitations share the path today |
| D39 | Which performance indicators are partner-visible, how they are calculated and who publishes them | proposed contract in `docs/api/proposed-performance-contract.md`; P2-11 | Do not build until D30 is approved; start with application turnaround and document-completeness only | Scorecards shown to partners become commitments |

## Added 2026-11-11 (gap-closure pass 2). Features were built; these answers finish them

| Id | Question | Affected code | Recommended default | Consequence |
|---|---|---|---|---|
| D40 | Secrets API: do you want secrets writable through the admin API at all? | none built; A-12b | No. Keep secrets in Render environment variables | An API needs an encryption key, rotation and an audit design |
| D41 | PDF and native Excel exports: approve adding a library (openpyxl, reportlab)? | reports; A-14d | CSV only until needed | New dependency and attack surface |
| D42 | Which email categories may partners switch off? Today only `account` is mandatory; `application` and `acknowledgement` are optional | `notifications/preferences.py` | Make `application` decisions mandatory too | Partners could miss decisions if optional |
| D43 | Approved list of staff sender labels for partner messages (today the constant `CoralSwift Team`) | `collaboration/constants.py` | Keep one label | none |
| D44 | Allowed values for `company_type`, `operating_model`, assessment `outcome`, and indicator keys (all free text/slug today) | profile, assessment, performance | Define short lists per field, then enforce | Free text produces inconsistent reports |
| D45 | Reviewer reach: reviewers see projects, messages, onboarding and performance only for organisations whose application is assigned to them. Should BDMs get any of this? | `collaboration/service.py::org_scope` | No | Matches the existing document scoping |


## Final owner round 2026-11-11 - what was applied, conflicts, and what is still open

Applied: D1, D2 (kept `ACCOUNT_DEACTIVATED`/`ACCOUNT_LOCKED` only after the correct password; invited accounts stay generic), D3 (configurable targets), D4 (deletion blocked), D5, D7, D9 (pass/fail/N-A), D10 (configurable tasks), D11, D12, D13, D14, D16, D18, D22, D24, D25, D26, D27, D28, D33 (quarantine-only), D34 (configurable SLA), D38, D40, D41, D42, D43, D45 (BDM read-only, assigned organisations).

### Conflicts found (reported, not silently resolved)
1. **D44 and D39 were approved in one message and "do not apply until I confirm" in two later ones.** Not enforced. Enums stay free text/slug in the database and API until you confirm. Proposed values for review: `company_type` private_limited, public_limited, partnership, llp, proprietorship, nonprofit, other; `operating_model` onsite, remote, hybrid, multi_location; assessment outcome approved, rejected, needs_clarification, pending; performance keys `application_turnaround_days`, `document_completeness_percentage`. Proposed calculations (for review): turnaround days = (decided_at - submitted_at) in days per decided application in the period, averaged; completeness percentage = required document categories with an accepted, unexpired, current version / required categories, where the required list is still pending D6. Confirm and the constraints are a small migration.
2. **D19 (profile changes only by change request) vs the implementation**: partners edit their profile directly (`PUT /partner/organization`, all fields `direct_update: true`) and the change-request flow exists beside it. Changing this alters behaviour the frontend already uses, so it was not changed. Decide: keep direct partner edits for non-sensitive fields, or force every change through approval.
3. **D15 vs the enquiry reply endpoint** built in the previous pass: now off by default (`ENQUIRY_REPLY_ENABLED=false`).
4. **D45 assignment meaning**: the repository has no "organisation assigned to a BDM" field. Implemented as: the partner enquiry that created the organisation is assigned to that BDM. Organisations created by direct invitation have no source enquiry, so BDMs see none of them. Confirm or define an explicit assignment.
5. **D2 wording** says generic inactive-account errors; the existing behaviour is 403 `ACCOUNT_DEACTIVATED` after a correct password. Kept.

### Questions that still block something (one per line)
1. D3: named queue owners and backups, and the response target per queue (24-48 h is proposed; nothing is set).
2. D6: thresholds and mandatory document categories per pathway.
3. D9: final checklist items and who may approve at each stage.
4. D10: initial onboarding stages, required tasks, owners and deadlines (you approved six suggested stages in one message but the list was not supplied; none were created).
5. D34: legally approved period and who handles requests.
6. D39/D44: confirm the enumerations and indicator calculations above.
7. D19: direct partner edits or change requests only (conflict 2).
8. D45: confirm the BDM assignment definition (conflict 4).
9. D4: retention periods after legal review.
10. External items: see `docs/EXTERNAL-CONFIGURATION-CHECKLIST.md`.


## Final pass 2026-11-11 (binding decisions applied)
Resolved and implemented: D44 (enums enforced in API/OpenAPI; database checks added NOT VALID so existing rows are untouched), D39 (two indicators, fixed definitions, unavailable states), D45 (explicit `organization_bdm_assignments`; the earlier "originating enquiry" proxy was removed), D19 (change requests for existing values), D3 defaults, D34 defaults, D10 template mechanism, D9 pending state.

Still not decided (nothing invented): D3 named owners/backups; D6 thresholds and required categories per pathway (`required_documents.<pathway>` settings stay unset, so completeness is "unavailable"); D4 retention periods; D10 initial task list (template is empty); legal confirmation of D34.
Open implementation note: the 48 h escalation target is a default constant and setting, but escalation still triggers when the 24 h first-response target is missed.
