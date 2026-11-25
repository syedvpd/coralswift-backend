# Document Storage, Antivirus & Email Notification Audit

**Storage Backend:** Local (dev) / S3-compatible Supabase Storage (production)  
**Email Backend:** Console (dev) / Brevo Transactional API (production)  
**Malware Scanner Backend:** Quarantine-only mode (`SCANNER_BACKEND=none`)

---

## 1. Document Lifecycle & Storage Pipeline

```
[Client Upload: POST /documents/upload or /partner/documents]
                           │
                           ▼
             [MIME & Magic Bytes Validation]
             Allowed: PDF, DOCX, XLSX, PNG, JPG (Max 10 MiB)
                           │
                           ▼
          [Encrypted Storage in Private Bucket]
          s3://coral-swift-partner-documents/{org_id}/{doc_id}
                           │
                           ▼
                   [Malware Scan Gate]
       Is ClamAV active? ──► NO ──► upload_status: "quarantined"
                           │        scan_status: "not_scanned"
                           ▼
               [Access & Download Gate]
     GET /api/v1/partner/documents/{id}/download
     - Authentication Verified
     - Org Ownership Verified
     - Download Event Audited in `activities`
```

### Key Audit Findings:
1. **Malware Scanning Gap:**
   - The backend contains a complete ClamAV integration adapter (`app/integrations/scanner.py`), but in production it is disabled (`SCANNER_BACKEND=none`).
   - Consequently, all documents are flagged `quarantined` and `not_scanned`. The frontend requirement for real-time clean file attestation cannot be met until a live ClamAV daemon is provisioned.
2. **Private Document Protection:**
   - Uploaded files are stored in private buckets without public read ACLs.
   - Files can only be downloaded via authenticated API streaming endpoints (`/download`) with audit logging. Signed URLs are short-lived and never permanently exposed.

---

## 2. Email & Notification System Audit

### Brevo Integration Architecture
- Handled by `app/integrations/email.py` (`BrevoEmailSender`).
- Direct HTTP REST integration to `https://api.brevo.com/v3/smtp/email` using `api-key` header.
- Transactional templates supported:
  - Account Invitation (`partner.invitation`)
  - Password Reset (`auth.password_reset`)
  - Public Submission Acknowledgement (`enquiry.acknowledgement`)
  - Internal Staff Notification (`admin.lead_notification`)
  - Information Request / Task Notification (`partner.notification`)

### Outbox & Resilience Pattern
1. When an event occurs (e.g. enquiry submitted, invitation issued), a notification record is saved to the `notifications` outbox table within the same DB transaction.
2. FastAPI `BackgroundTasks` calls `dispatch_notifications`, picking up queued rows and transmitting them to Brevo.
3. If Brevo fails or rate limits, the notification remains in `queued` status and is retried up to 5 times (`NOTIFICATION_MAX_RETRIES`) via the maintenance worker.
4. **Bounce Handling:** A webhook receiver at `/api/v1/notifications/webhook` processes Brevo bounce/drop webhooks and updates `user.email_deliverability` status.

