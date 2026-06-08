# Task Breakdown

This document tracks the notable MVP work completed so far and the next implementation steps.

## Completed

### Branding And UI

- Renamed visible dashboard brand from `AgroLedger` to `OPEKEPE`.
- Kept internal package/API names stable for compatibility.
- Restyled the dashboard with a Python/Django-inspired visual direction.
- Added Python/Django palette, console-style sidebar, admin-style cards, and updated chart colors.
- Moved `EL / EN` language buttons to the bottom-left of the UI.

### Browser Dashboard

- Kept the dashboard served from the local Python HTTP app.
- Added role selector to sign-in.
- Added role-aware navigation and role-aware dashboard panels.
- Added `Reports` section.
- Added `Applicants` admin section.

### Applicant Role

- Applicant can view:
  - Overview
  - Documents
  - Land
  - Forecast
  - Finance
  - Crisis
- Applicant can submit evidence and documents.
- Added applicant finance/techno-economic view:
  - Expected subsidy
  - Subsidies owed back / offsets
  - Expected disbursable amount
  - Projected gross crop income
  - Projected by-product income
  - Cost exposure
  - Estimated net margin
  - Market cap at max yield
  - Market-flow events
- Added applicant crisis view:
  - Crisis evidence guidance
  - Weather/damage/financial evidence categories
  - Government coverage estimate
  - Crisis payment scenarios

### Admin Role

- Admin can view all sections:
  - Overview
  - Applicants
  - Documents
  - Land
  - Forecast
  - Audit
  - Finance
  - Crisis
  - Reports
- Added admin role-management table.
- Added admin applicants/operations page:
  - Total applicants
  - Documents in system
  - Audit events
  - Economic records
  - Crisis cases
  - All applicants table
  - Load-balancing table
  - Service-window overview
  - Admin quick actions

### Auditor Role

- Auditor view is intentionally scoped to:
  - Overview
  - Documents
  - Finance
- Auditor document view shows:
  - Document object
  - File name
  - Audit mode
  - Risk
- Auditor finance view shows related economic-analysis objects:
  - Declared yield plan
  - Subsidy calculation
  - Debt offset
  - First-sale deductions
  - By-product market value
  - Maximum market cap

### Reporting

- Added local JSON report generation for admin/auditor roles.
- Reports include:
  - Applicant identity
  - Integrity status
  - Documents
  - Audit findings
  - Finance exposure
  - Crisis state

### API And Data

- Added `applicants` to `/dashboard/data`.
- Preserved existing JSON API endpoints.
- Preserved demo SQLite database workflow.

### Verification

- Python compile check passes.
- Unit/API test suite passes with 14 tests.

## In Progress / Known MVP Limitations

- Role permissions are currently client-side UI rules.
- There is no real login or persisted user account table yet.
- Admin/auditor assignment is not persisted.
- Reports are generated client-side and not stored.
- External government, cadastral, weather, AADE/myDATA, and payment integrations are still demo concepts.
- UI tests are not yet implemented.

## Next Steps

### Authentication And Authorization

- Add persisted users.
- Add server-side sessions.
- Store role assignments in SQLite.
- Enforce role permissions on API routes.
- Add applicant ownership checks.
- Add auditor assignment to specific applicant records or regions.

### Admin Operations

- Persist load-balancing queue state.
- Add queue assignment actions.
- Add status transitions for each operational window.
- Add admin filters for applicant status, risk, region, and document completeness.

### Auditor Workflow

- Add audit case assignment.
- Add auditor notes and decisions.
- Add document-level status transitions.
- Add economic-object review status.
- Add report approval/sign-off.

### Applicant Workflow

- Add richer crisis incident submission forms.
- Add structured evidence metadata.
- Add applicant-facing document completeness progress.
- Add market-flow timeline and exportable finance summary.

### Reporting

- Generate reports server-side.
- Store report snapshots.
- Add PDF/CSV export.
- Add immutable audit trail for generated reports.

### Platform

- Add OpenAPI docs.
- Add end-to-end UI tests.
- Move geospatial storage to PostGIS for production.
- Add official registry, weather, cadastral, AADE/myDATA, and payment integrations.
