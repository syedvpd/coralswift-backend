# PRD v2.0 Compliance Matrix & Traceability Audit

**Reference Specification:** CoralSwift Product Requirement Document (PRD) v2.0  
**Audit Standard:** Code Verification, Database Schema Inspection, and Automated Tests.

---

## 1. Compliance Summary by PRD Section

| Section | Focus Area | Requirement Count | Verified Complete | Partial | Missing / Non-Compliant | Compliance % |
|---|---|---|---|---|---|---|
| **s.8 – 10** | Public Website & Intake | 12 | 10 | 2 | 0 | 83% |
| **s.11 & 28**| Partner Evaluation Stages (1–9)| 18 | 10 | 5 | 3 | 55% |
| **s.12** | Partner Application Form Fields | 14 | 14 | 0 | 0 | 100% |
| **s.13** | Document Management & Storage | 10 | 7 | 3 | 0 | 70% |
| **s.14** | Admin Console Management | 15 | 11 | 3 | 1 | 73% |
| **s.15** | Collaboration & Engagement | 12 | 11 | 1 | 0 | 92% |
| **s.16 – 19**| Security, Auth & RBAC | 16 | 13 | 2 | 1 | 81% |
| **s.20 – 22**| Technical Architecture & Operations| 14 | 10 | 3 | 1 | 71% |
| **Total** | **Comprehensive System Scope** | **111** | **86** | **19** | **6** | **77.5%** |

---

## 2. Detailed Non-Compliance & Deviation Register

### Deviation 1: Ingestion Bridge Disconnection (PRD s.11 / s.12)
- **PRD Requirement:** Submission of a partner application on the public website must enter the Partner Evaluation pipeline and notify the designated recipient and reviewer queue.
- **Observed Code:** Submissions write to `enquiries` table only. Reviewers querying `portal_applications` see no records.
- **Classification:** **NON-COMPLIANT (CRITICAL WORKFLOW BREAK)**

### Deviation 2: Segregation of Duties & Missing Role (PRD s.14 / s.28)
- **PRD Requirement:** Operational reviewers make recommendations; final approval for pilot onboarding and commercial commitments requires authorized management approval.
- **Observed Code:** Role `authorized_management` does not exist in `StaffRole`. Any user with `partner_reviewer` can unilaterally execute terminal transition to `pilot_onboarding`.
- **Classification:** **NON-COMPLIANT (CRITICAL SECURITY & GOVERNANCE RISK)**

### Deviation 3: BDM Application Ownership (PRD s.11 / s.14)
- **PRD Requirement:** Super Administrator assigns a Business Development Manager as operational owner. BDM oversees the application, reviews documents, and coordinates reviewers.
- **Observed Code:** `PortalApplication` model only supports `assigned_reviewer_id`. BDM accounts receive 403 Forbidden on all reviewer application endpoints.
- **Classification:** **NON-COMPLIANT (CRITICAL OPERATIONAL GAP)**

### Deviation 4: Active Malware Scanning (PRD s.13 / s.19)
- **PRD Requirement:** Uploaded files must be scanned for malware before being made available for review or download.
- **Observed Code:** ClamAV daemon is not provisioned; backend runs with `SCANNER_BACKEND=none`. All files remain in `quarantined` state.
- **Classification:** **PARTIALLY COMPLIANT (Accepted quarantine risk per D33; scanner offline)**

