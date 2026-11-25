# Partner Application PRD Compliance Report (Report 5)

**Baseline:** CoralSwift PRD v2.0 Section 11 ("Partner Evaluation & Allocation Workflow") & Section 12 ("Partner Application Form").

---

## 1. Compliance Matrix by Explicit PRD Clause

| PRD Section | Requirement Description | Implementation Status | Technical Evidence |
|---|---|---|---|
| **s.11.1** | Partner Expression of Interest & Ingestion | 🟡 PARTIAL | `enquiries/partner` saves form, but does not bridge to reviewer applications. |
| **s.11.2** | Eligibility Verification (Stage 4) | ✅ VERIFIED | Checklist items and human review verification in `review_workflow`. |
| **s.11.3** | Capability Review (Stage 5) | 🟡 PARTIAL | General checklist exists; dedicated 1–5 structured rating table missing. |
| **s.11.4** | Commercial & Legal Review (Stage 6) | 🟡 PARTIAL | Status transition exists; dedicated NDA/IP/terms sign-off table missing. |
| **s.11.5** | Pilot Onboarding (Stage 8) | ✅ VERIFIED | Onboarding record created, milestones tracked, tasks assigned to partner. |
| **s.11.6** | Scale-Up Evaluation (Stage 9) | ✅ VERIFIED | Performance metrics, turnaround days, and scorecards published. |
| **s.11.7** | Rejection and Reopening | ✅ VERIFIED | Withdrawn/rejected states final; super admin can reopen via `/reopen`. |
| **s.12.1** | Organization Information Fields | ✅ VERIFIED | All legal name, trading name, address, tax ID, website fields captured. |
| **s.12.2** | Authorized Contact Details | ✅ VERIFIED | Primary contact name, email, phone, role stored in snapshot. |
| **s.12.3** | Turnover & Employee Strength | ✅ VERIFIED | `workforce_size` and `annual_turnover` enums captured. |
| **s.12.4** | Eight Evidence Document Categories | ✅ VERIFIED | Defined in `EvidenceCategory` enum; uploaded to private storage. |
| **s.12.5** | Screening Criteria Not Hardcoded | ✅ VERIFIED | 3 yrs / 50 staff / 2 Cr criteria are proposed only; zero auto-rejections. |
| **s.14.3** | BDM Ownership of Assigned Applications | 🔴 NON-COMPLIANT | BDM excluded from reviewer queue and model has no `assigned_bdm_id`. |
| **s.14.4** | Segregation of Duties for Pilot Approval | 🔴 NON-COMPLIANT | Reviewer can approve pilot directly without management authorization. |

