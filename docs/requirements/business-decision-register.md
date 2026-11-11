# Business Decision Register (owner action required)

Created 2026-11-09. Nothing here is decided. Until the owner answers, every affected requirement stays **BLOCKED** in `prd-master-register.md`. Engineers must not invent answers. "Setting" shows where the answer is entered once decided.

| # | Decision needed | Why it matters / what it unlocks | Where it is applied | Affected rows | Owner | Status |
|---|---|---|---|---|---|---|
| 1 | Queue owners and backup owners per queue (general, project, partner, strategic, meeting) | Routing assigns an owner or the out-of-office backup; unassigned today | settings `route.owner.<queue>`, `route.backup.<queue>` | 1.15, 28.4 | Business owner | OPEN |
| 2 | SLA first-response hours per queue; escalation recipient per queue | Sets `response_due_at`, SLA breach flag and escalation emails. Acknowledgement time promises stay off until set | settings `sla.<queue>`, `escalation.email.<queue>`, `ack_promise_enabled` | 28.11 | Business owner | OPEN |
| 3 | Official contact details (domain, business email, phone, registered address or "omit", authorised representative) | Launch gate; public contact endpoint shows confirmed values only | settings `contact.*` (and `.omitted`) | 28.10 | Business owner | OPEN |
| 4 | Privacy notice text and version; consent wording | Consent record stores the version; currently `draft-unapproved` | env `PRIVACY_NOTICE_VERSION`, frontend text | 1.x consent, 3.12 | Owner + legal | OPEN |
| 5 | Retention periods (partner documents, enquiries, strategic/financial records) and deletion policy | The retention purge and deletion workflow stay inert until a period is set | setting `retention.partner_document_days`; policy for other data | 2.15, 3.12, 28.8 | Owner + legal | OPEN |
| 6 | Named incident owner and incident process | Required by s.29 and s.19 | operations | 0.13, 3.13 | Owner | OPEN |
| 7 | Partner access: invitation-only or self-registration | Today invitation-only | code change only if self-registration is chosen | 2.5 | Business owner | OPEN |
| 8 | Who may assign reviewers | Today super administrators | `reviews/` assignment permission | 2.22 | Business owner | OPEN |
| 9 | Explicit "approved" application status | The six PRD stages have no final "approved" state; decisions are reviewer records | status model (needs a migration if added) | 2.23 | Business owner | OPEN |
| 10 | Eligibility thresholds (3 years, 50 personnel, INR 2 crore): which pathway each applies to | Shown as "proposed" with applicability "to be confirmed"; never auto-decides | `catalog/` criteria data | 1.17, 28.6 | Business owner | OPEN |
| 11 | Should Business Development Managers see strategic/M&A enquiries? | Default today: no | `admin/service.py::visible_types` | 3.4 | Owner | OPEN (default: no access) |
| 12 | Content approver role | Today only a super administrator approves content | `content/` approval permission | 3.6 | Owner | OPEN |
| 13 | Malware scanning: choose a scanner, or formally accept quarantine-only uploads | **DECIDED 2026-11-10: the owner formally accepts quarantine-only uploads and does not want a scanner or ClamAV.** All uploads stay `quarantined`; the system never claims files are scanned or clean. Revisit if the business later wants a scanner | documented acceptance; no code change | 1.8, 2.14 | Owner | DECIDED (accepted risk, recorded in chat 2026-11-10) |
| 14 | KPI definitions: "qualified enquiry", "meets initial screening criteria", "enquiry to qualified discussion" conversion | Not computed because humans decide and no definition exists | KPI endpoint once defined | 3.10 | Business owner | OPEN |
| 15 | Monitoring, error tracking, uptime alerts and backup ownership (production backup/PITR policy, restore test cadence) | Required before launch | hosting/operations | 0.13, 0.14 | Owner / ops | OPEN |
| 16 | Calendar provider for meeting confirmation (or accept staff-attested confirmation) | Meetings are confirmed manually by staff today | new adapter | 1.5 | Business owner | OPEN |
| 17 | Staging and production hostnames, frontend origins, Brevo sender domain | Needed for CORS, trusted hosts, Turnstile hostnames, SPF/DKIM/DMARC | env vars | 0.6, 1.26 | Owner / ops | OPEN |
| 18 | Partner, client and testimonial publication data and permissions | Claims register is ready but empty | `/admin/content-claims` | 28.1, 28.2 | Business owner | OPEN |
# Decision-register status update (2026-11-11)

The frontend's recommendations are recorded as recommendations only in `docs/business-decisions-required.md`; none is treated as owner approval. Current implementation and audit evidence are in `docs/phase-scope/REQUIREMENT_AUDIT_PHASES_1_3.md`. Migrations `0013`-`0015` are applied to development (`0015` head); no backup was created, per owner instruction. Remaining policy decisions and the owner inputs required are listed in the business-decision document.
