# Proposed partner performance API (NOT implemented, awaiting D30 and D39)

Recorded 2026-11-11 so the frontend can review the shape. Nothing here exists in `openapi.json`. Every indicator needs an owner-approved definition before code is written.

| Endpoint | Role | Purpose |
|---|---|---|
| `GET /partner/performance/summary` | partner | Indicators published for the caller's organisation, each `{key, label, value, unit, period, definition}` |
| `GET /partner/performance/trends?indicator=&from=&to=` | partner | Monthly series for one published indicator |
| `GET /partner/performance/scorecards` | partner | Published scorecards `{id, period, items[], published_at}` |
| `GET /partner/performance/feedback` | partner | Published reviewer feedback `{id, period, text, published_at}` |
| `GET /partner/performance/export.csv` | partner | CSV of the published rows for the caller's organisation only |
| `POST /admin/organizations/{id}/performance/publish` | super administrator | Publish or unpublish a period; nothing is partner-visible until published |

Rules: organisation comes from the token; unpublished data never appears in partner payloads; each indicator carries its calculation text; PDF export only if D26 is approved. Candidate indicators (all need approval): application turnaround days, document completeness, time to respond to information requests.
