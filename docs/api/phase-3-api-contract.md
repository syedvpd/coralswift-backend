# Phase 3 API Contract (admin, content, engagement)

Auth: staff bearer token with completed MFA. SA = super_administrator, BDM = business_development_manager, CA = content_administrator. Wrong role -> 403; hidden resources -> 404.
Lists use `page`, `page_size` (max 100) and `meta`. Mutations and exports write to `activities` (ids and field names only, never free-text notes or confidential content).

## Admin (`/api/v1/admin`)
| Endpoint | Roles | Notes |
|---|---|---|
| `GET /overview` | SA, BDM | counters; SA also application counts + recent activity |
| `GET /enquiries`, `GET /enquiries/{id}` | SA, BDM | filters `type,status,priority,assigned_user_id,unassigned,overdue,q,created_from,created_to`; BDM never sees strategic enquiries or financial fields |
| `PATCH /enquiries/{id}`, `POST /enquiries/{id}/assign` | SA, BDM | status/priority; owner must be an active BDM/SA (strategic: SA only) |
| `POST /enquiries/{id}/follow-ups`, `.../{fid}/complete` | SA, BDM | communication history, `next_follow_up_at` |
| `GET /enquiries/{id}/documents/{doc}/download` | SA, BDM | audited |
| `POST /meetings/{enquiry_id}/confirm|decline|cancel` | SA, BDM | confirm needs `calendar_checked=true` (also a DB constraint); requester is emailed |
| `GET /organizations`, `/organizations/{id}`, `POST /organizations/{id}/status` | SA, BDM (status: SA) | partner database; BDM limited view |
| `GET/POST /users`, `POST /users/{id}/role|activate|deactivate|mfa-reset` | SA | staff management; no self changes; last super administrator protected |
| `GET /audit` | SA | filters on type, action, actor, organization, dates |
| `GET /settings`, `PUT/DELETE /settings/{key}` | SA | keys: `retention.partner_document_days`, `expiry_reminder_days` |
| `GET /notification-templates`, `PUT/DELETE /notification-templates/{key}`, `POST .../{key}/preview` | SA | override built-in emails; allowed placeholders only (`$name $reference $status_label $link $enquiry_type $company $category $expires_on $meeting_time`); single-line subject |
| `GET /profile-change-requests`, `POST /profile-change-requests/{id}/decide` | SA | approval applies the change through the revision-tracked update |
| `GET /privacy-requests`, `POST /privacy-requests/{id}` | SA | data access / correction / deletion requests |
| `GET /reports/enquiries.csv` | SA, BDM | same filters as the list, 10,000-row cap, formula-safe, BDM excludes strategic |
| `GET /reports/applications.csv`, `/reports/newsletter.csv` | SA | audited |
| `GET /reports/kpis` | SA, BDM | enquiries by type/source/status, avg hours to first follow-up, overdue follow-ups, meeting counts; SA: application completion, recorded eligibility outcomes, document review turnaround. No targets |

## Content (`/api/v1/admin/content`, CA or SA)
`POST` create draft, `GET` list/detail, `PATCH` edit (draft only, stores a version), `GET /{id}/versions`, `POST /{id}/submit` (draft -> in_review), `POST /{id}/approve|reject` (**SA only**), `POST /{id}/publish|unpublish|reopen|archive`, `POST /{id}/attachment` (draft only; versioned downloadable document).
Nothing is public until approved and published; reopening content takes it off the site.

## Public (`/api/v1`)
| Endpoint | Notes |
|---|---|
| `GET /content`, `/content/{slug}`, `/content/sitemap`, `/content/{slug}/download` | published only; search `q`, `type`, `category`, `tag`; related items; `Cache-Control: public, max-age=300` |
| `POST /meetings` | same fields as other forms plus `purpose`, `preferred_slots` (1-3 future slots), IANA `timezone`; creates a request, never a booking; follow with `GET /enquiries/{ref}/status` |
| `POST /newsletter/subscribe|unsubscribe` | consent recorded; unsubscribe needs the token returned at subscription; nothing is sent by this API |
| `POST /privacy/requests` | `{email, kind: access|correction|deletion, details?}`; reference returned, acknowledgement emailed |

## Partner dashboard additions (`/api/v1/partner`)
`POST|GET /organization/change-requests`, `GET /notifications` (type + status only), `GET /enquiries` (history).
