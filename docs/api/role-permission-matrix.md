# Role permission matrix (generated from route guards)

Generated from `endpoint_table(create_app())`. `allow` = role passes the route guard; `403` otherwise. Service-layer limits apply on top: reviewers reach only organisations/applications assigned to them; BDMs read partner collaboration data only for organisations explicitly assigned to them and cannot write; strategic enquiries are super-administrator only; BDMs never see financial documents. `GET /auth/permissions` returns the live matrix; `test_permission_matrix_matches_real_enforcement` checks it against enforcement.

Columns: SA super_administrator, BDM business_development_manager, PR partner_reviewer, CA content_administrator.

| Method | Path | SA | BDM | PR | CA |
|---|---|---|---|---|---|
| GET | `/api/v1/admin/accounts` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/accounts/metrics` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/accounts/{user_id}` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/accounts/{user_id}/invitation/resend` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/accounts/{user_id}/invitation/revoke` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/accounts/{user_id}/password-reset` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/accounts/{user_id}/reactivate` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/accounts/{user_id}/suspend` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/assignees` | allow | allow | allow | allow |
| GET | `/api/v1/admin/audit` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/audit.csv` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/audit/actions` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/audit/{activity_id}` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/content` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/content` | allow | 403 | 403 | allow |
| GET | `/api/v1/admin/content-claims` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/content-claims` | allow | 403 | 403 | allow |
| PATCH | `/api/v1/admin/content-claims/{claim_id}` | allow | 403 | 403 | allow |
| GET | `/api/v1/admin/content/{item_id}` | allow | 403 | 403 | allow |
| PATCH | `/api/v1/admin/content/{item_id}` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/content/{item_id}/approve` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/content/{item_id}/archive` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/content/{item_id}/attachment` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/content/{item_id}/publish` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/content/{item_id}/reject` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/content/{item_id}/reopen` | allow | 403 | 403 | allow |
| DELETE | `/api/v1/admin/content/{item_id}/schedule` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/content/{item_id}/schedule` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/content/{item_id}/submit` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/content/{item_id}/unpublish` | allow | 403 | 403 | allow |
| GET | `/api/v1/admin/content/{item_id}/versions` | allow | 403 | 403 | allow |
| GET | `/api/v1/admin/documents` | allow | 403 | allow | 403 |
| GET | `/api/v1/admin/documents/{document_id}/history` | allow | 403 | allow | 403 |
| POST | `/api/v1/admin/documents/{document_id}/purge` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/enquiries` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/enquiries/{enquiry_id}` | allow | allow | 403 | 403 |
| PATCH | `/api/v1/admin/enquiries/{enquiry_id}` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/enquiries/{enquiry_id}/activity` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/enquiries/{enquiry_id}/assessment` | allow | allow | 403 | 403 |
| POST | `/api/v1/admin/enquiries/{enquiry_id}/assessment` | allow | allow | 403 | 403 |
| POST | `/api/v1/admin/enquiries/{enquiry_id}/assign` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/enquiries/{enquiry_id}/documents` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/enquiries/{enquiry_id}/documents/{document_id}/download` | allow | allow | 403 | 403 |
| POST | `/api/v1/admin/enquiries/{enquiry_id}/follow-ups` | allow | allow | 403 | 403 |
| PATCH | `/api/v1/admin/enquiries/{enquiry_id}/follow-ups/{followup_id}` | allow | allow | 403 | 403 |
| POST | `/api/v1/admin/enquiries/{enquiry_id}/follow-ups/{followup_id}/cancel` | allow | allow | 403 | 403 |
| POST | `/api/v1/admin/enquiries/{enquiry_id}/follow-ups/{followup_id}/complete` | allow | allow | 403 | 403 |
| POST | `/api/v1/admin/enquiries/{enquiry_id}/reply` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/feed` | allow | allow | allow | allow |
| POST | `/api/v1/admin/feed/read-all` | allow | allow | allow | allow |
| POST | `/api/v1/admin/feed/{item_id}/archive` | allow | allow | allow | allow |
| POST | `/api/v1/admin/feed/{item_id}/read` | allow | allow | allow | allow |
| GET | `/api/v1/admin/follow-ups` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/launch-readiness` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/media` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/media` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/media/{asset_id}/archive` | allow | 403 | 403 | allow |
| GET | `/api/v1/admin/media/{asset_id}/file` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/media/{asset_id}/publish` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/media/{asset_id}/unpublish` | allow | 403 | 403 | allow |
| POST | `/api/v1/admin/meetings/{enquiry_id}/cancel` | allow | allow | 403 | 403 |
| POST | `/api/v1/admin/meetings/{enquiry_id}/confirm` | allow | allow | 403 | 403 |
| POST | `/api/v1/admin/meetings/{enquiry_id}/decline` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/notification-templates` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/notification-templates/placeholders` | allow | 403 | 403 | 403 |
| DELETE | `/api/v1/admin/notification-templates/{key}` | allow | 403 | 403 | 403 |
| PUT | `/api/v1/admin/notification-templates/{key}` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/notification-templates/{key}/preview` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/notification-templates/{key}/versions` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/notification-templates/{key}/versions/{version_no}/activate` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/notifications` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/notifications/dispatch` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/notifications/{notification_id}/retry` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/onboarding-template` | allow | 403 | allow | 403 |
| PUT | `/api/v1/admin/onboarding-template` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/organizations` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/organizations/{org_id}` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/organizations/{org_id}/activity` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/organizations/{org_id}/bdm-assignments` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/organizations/{org_id}/bdm-assignments` | allow | 403 | 403 | 403 |
| DELETE | `/api/v1/admin/organizations/{org_id}/bdm-assignments/{user_id}` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/organizations/{org_id}/revisions` | allow | allow | 403 | 403 |
| POST | `/api/v1/admin/organizations/{org_id}/status` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/overview` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/privacy-requests` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/privacy-requests/{request_id}` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/privacy-requests/{request_id}/execute` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/profile-change-requests` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/profile-change-requests/{request_id}/decide` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/reports/applications.csv` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/reports/communications` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/reports/document-review` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/reports/enquiries.csv` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/reports/follow-ups` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/reports/kpis` | allow | allow | 403 | 403 |
| GET | `/api/v1/admin/reports/newsletter.csv` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/security-policy` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/settings` | allow | 403 | 403 | 403 |
| DELETE | `/api/v1/admin/settings/{key}` | allow | 403 | 403 | 403 |
| PUT | `/api/v1/admin/settings/{key}` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/users` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/users` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/users/{user_id}` | allow | 403 | 403 | 403 |
| PATCH | `/api/v1/admin/users/{user_id}` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/users/{user_id}/activate` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/users/{user_id}/activity` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/users/{user_id}/deactivate` | allow | 403 | 403 | 403 |
| POST | `/api/v1/admin/users/{user_id}/role` | allow | 403 | 403 | 403 |
| GET | `/api/v1/admin/workload` | allow | allow | 403 | 403 |
| GET | `/api/v1/reviewer/applications` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/applications/{application_id}` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/applications/{application_id}/assign` | allow | 403 | 403 | 403 |
| PUT | `/api/v1/reviewer/applications/{application_id}/checklist` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/applications/{application_id}/document-requests` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/applications/{application_id}/document-requests` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/applications/{application_id}/documents/{document_id}/download` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/applications/{application_id}/documents/{document_id}/review` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/applications/{application_id}/eligibility-verifications` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/applications/{application_id}/eligibility-verifications` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/applications/{application_id}/exceptions` | allow | 403 | 403 | 403 |
| GET | `/api/v1/reviewer/applications/{application_id}/history` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/applications/{application_id}/information-requests` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/applications/{application_id}/messages` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/applications/{application_id}/notes` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/applications/{application_id}/notes` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/applications/{application_id}/reopen` | allow | 403 | 403 | 403 |
| GET | `/api/v1/reviewer/applications/{application_id}/review` | allow | 403 | allow | 403 |
| PUT | `/api/v1/reviewer/applications/{application_id}/stage-owners/{stage}` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/applications/{application_id}/transition` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/collaboration` | allow | allow | allow | 403 |
| POST | `/api/v1/reviewer/collaboration` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/collaboration/{item_id}` | allow | allow | allow | 403 |
| PATCH | `/api/v1/reviewer/collaboration/{item_id}` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/collaboration/{item_id}/close` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/collaboration/{item_id}/reply` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/collaboration/{item_id}/share` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/collaboration/{item_id}/unshare` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/document-requests/{request_id}/cancel` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/invitations` | allow | 403 | 403 | 403 |
| GET | `/api/v1/reviewer/onboarding` | allow | allow | allow | 403 |
| POST | `/api/v1/reviewer/onboarding` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/onboarding/{record_id}` | allow | allow | allow | 403 |
| POST | `/api/v1/reviewer/onboarding/{record_id}/complete` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/onboarding/{record_id}/tasks` | allow | 403 | allow | 403 |
| PATCH | `/api/v1/reviewer/onboarding/{record_id}/tasks/{task_id}` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/organizations/{organization_id}/documents` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/organizations/{organization_id}/documents/{document_id}/versions` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/organizations/{organization_id}/performance` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/organizations/{organization_id}/performance` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/organizations/{organization_id}/performance-feedback` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/organizations/{organization_id}/performance-feedback` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/organizations/{organization_id}/performance/compute` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/organizations/{organization_id}/team` | allow | allow | allow | 403 |
| GET | `/api/v1/reviewer/partner-messages` | allow | allow | allow | 403 |
| POST | `/api/v1/reviewer/partner-messages` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/performance-feedback/{feedback_id}/{action}` | allow | 403 | allow | 403 |
| PATCH | `/api/v1/reviewer/performance/{entry_id}` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/performance/{entry_id}/publish` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/performance/{entry_id}/unpublish` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/projects` | allow | allow | allow | 403 |
| POST | `/api/v1/reviewer/projects` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/projects/{project_id}` | allow | allow | allow | 403 |
| PATCH | `/api/v1/reviewer/projects/{project_id}` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/projects/{project_id}/documents` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/projects/{project_id}/milestones` | allow | 403 | allow | 403 |
| PATCH | `/api/v1/reviewer/projects/{project_id}/milestones/{milestone_id}` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/projects/{project_id}/share` | allow | 403 | allow | 403 |
| POST | `/api/v1/reviewer/projects/{project_id}/unshare` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/transitions` | allow | 403 | allow | 403 |
| GET | `/api/v1/reviewer/workload` | allow | 403 | allow | 403 |

## Non-staff guarded routes

| Method | Path | Guard |
|---|---|---|
| POST | `/api/v1/auth/change-password` | authenticated |
| POST | `/api/v1/auth/logout` | authenticated |
| GET | `/api/v1/auth/me` | authenticated |
| PATCH | `/api/v1/auth/me` | authenticated |
| GET | `/api/v1/auth/permissions` | authenticated |
| DELETE | `/api/v1/auth/sessions` | authenticated |
| GET | `/api/v1/auth/sessions` | authenticated |
| DELETE | `/api/v1/auth/sessions/{session_id}` | authenticated |
| POST | `/api/v1/partner/account-closure` | partner |
| GET | `/api/v1/partner/account-closure/preview` | partner |
| GET | `/api/v1/partner/applications` | partner |
| POST | `/api/v1/partner/applications` | partner |
| GET | `/api/v1/partner/applications/{application_id}` | partner |
| PATCH | `/api/v1/partner/applications/{application_id}` | partner |
| GET | `/api/v1/partner/applications/{application_id}/history` | partner |
| GET | `/api/v1/partner/applications/{application_id}/messages` | partner |
| POST | `/api/v1/partner/applications/{application_id}/messages` | partner |
| GET | `/api/v1/partner/applications/{application_id}/readiness` | partner |
| POST | `/api/v1/partner/applications/{application_id}/resubmit` | partner |
| POST | `/api/v1/partner/applications/{application_id}/submit` | partner |
| POST | `/api/v1/partner/applications/{application_id}/withdraw` | partner |
| GET | `/api/v1/partner/discussions` | partner |
| GET | `/api/v1/partner/discussions/{item_id}` | partner |
| POST | `/api/v1/partner/discussions/{item_id}/respond` | partner |
| GET | `/api/v1/partner/document-requests` | partner |
| GET | `/api/v1/partner/document-requests/{request_id}` | partner |
| GET | `/api/v1/partner/documents` | partner |
| POST | `/api/v1/partner/documents` | partner |
| DELETE | `/api/v1/partner/documents/{document_id}` | partner |
| GET | `/api/v1/partner/documents/{document_id}` | partner |
| GET | `/api/v1/partner/documents/{document_id}/download` | partner |
| GET | `/api/v1/partner/documents/{document_id}/history` | partner |
| POST | `/api/v1/partner/documents/{document_id}/versions` | partner |
| GET | `/api/v1/partner/enquiries` | partner |
| GET | `/api/v1/partner/follow-ups` | partner |
| GET | `/api/v1/partner/follow-ups/{item_id}` | partner |
| POST | `/api/v1/partner/follow-ups/{item_id}/respond` | partner |
| GET | `/api/v1/partner/meetings` | partner |
| GET | `/api/v1/partner/meetings/{item_id}` | partner |
| POST | `/api/v1/partner/meetings/{item_id}/respond` | partner |
| GET | `/api/v1/partner/messages` | partner |
| POST | `/api/v1/partner/messages` | partner |
| GET | `/api/v1/partner/messages/{message_id}` | partner |
| POST | `/api/v1/partner/messages/{message_id}/read` | partner |
| POST | `/api/v1/partner/messages/{message_id}/unread` | partner |
| GET | `/api/v1/partner/notification-preferences` | partner |
| PUT | `/api/v1/partner/notification-preferences` | partner |
| GET | `/api/v1/partner/notifications` | partner |
| POST | `/api/v1/partner/notifications/read-all` | partner |
| GET | `/api/v1/partner/notifications/unread-count` | partner |
| POST | `/api/v1/partner/notifications/{notification_id}/read` | partner |
| POST | `/api/v1/partner/notifications/{notification_id}/unread` | partner |
| GET | `/api/v1/partner/onboarding` | partner |
| GET | `/api/v1/partner/organization` | partner |
| PUT | `/api/v1/partner/organization` | partner |
| GET | `/api/v1/partner/organization/change-requests` | partner |
| POST | `/api/v1/partner/organization/change-requests` | partner |
| GET | `/api/v1/partner/organization/completion` | partner |
| GET | `/api/v1/partner/organization/editable-fields` | partner |
| GET | `/api/v1/partner/organization/history` | partner |
| GET | `/api/v1/partner/performance/export.csv` | partner |
| GET | `/api/v1/partner/performance/feedback` | partner |
| GET | `/api/v1/partner/performance/scorecards` | partner |
| GET | `/api/v1/partner/performance/summary` | partner |
| GET | `/api/v1/partner/performance/trends` | partner |
| GET | `/api/v1/partner/privacy-requests` | partner |
| POST | `/api/v1/partner/privacy-requests` | partner |
| GET | `/api/v1/partner/projects` | partner |
| GET | `/api/v1/partner/projects/{project_id}` | partner |
| POST | `/api/v1/partner/projects/{project_id}/acknowledge` | partner |
| POST | `/api/v1/partner/projects/{project_id}/confirm` | partner |
| POST | `/api/v1/partner/projects/{project_id}/respond` | partner |
| POST | `/api/v1/partner/projects/{project_id}/submit-information` | partner |
| GET | `/api/v1/partner/team` | partner |
| POST | `/api/v1/partner/team/invitations` | partner |
| POST | `/api/v1/partner/team/transfer-ownership` | partner |
| DELETE | `/api/v1/partner/team/{membership_id}` | partner |
| GET | `/api/v1/partner/team/{membership_id}` | partner |
| POST | `/api/v1/partner/team/{membership_id}/activate` | partner |
| POST | `/api/v1/partner/team/{membership_id}/cancel` | partner |
| POST | `/api/v1/partner/team/{membership_id}/deactivate` | partner |
| POST | `/api/v1/partner/team/{membership_id}/resend` | partner |
| PATCH | `/api/v1/partner/team/{membership_id}/role` | partner |
