# Architecture

OPEKEPE System is a local Python MVP with a dependency-free HTTP server, SQLite persistence, a browser dashboard, and JSON API routes. The current implementation favors portability and demo clarity over production framework complexity.

The browser-facing product is branded as **OPEKEPE**. Internal Python names such as `agropekepe`, `AgroLedgerService`, and `agroledger.sqlite3` remain for compatibility with existing commands and tests.

## Runtime Shape

```text
Browser dashboard
  |
  | HTTP/JSON
  v
src/agropekepe/app.py
  |
  v
AgroLedgerService
  |
  v
AgroRepository
  |
  v
SQLite database
```

## Main Components

- `app.py`
  - Defines `AgroLedgerAPI`.
  - Serves the browser dashboard at `/`.
  - Serves JSON endpoints such as `/dashboard/data`, `/documents`, `/audit/events`, and `/annual-ledger`.
  - Contains the current inline HTML/CSS/JavaScript dashboard template.

- `cli.py`
  - Provides `init-db`, demo setup, and `serve` commands.

- `services.py`
  - Coordinates domain workflows: farmer registration, parcel registration, production enrollment, first sales, debts, subsidy calculations, crisis events, and compensation.

- `repository.py`
  - Owns SQLite persistence and audit-event recording.

- `eligibility.py`
  - Loads CAP-style rules and calculates subsidy eligibility.

- `integrations.py`
  - Holds adapter-style helpers for map/weather/remote-sensing concepts.

## Dashboard Architecture

The dashboard is currently a single inline HTML document embedded in `app.py`. It contains:

- OPEKEPE branding.
- Python/Django-inspired visual styling.
- Bottom-left `EL / EN` language switcher.
- Role selector at sign-in.
- Role-aware client-side navigation.
- Canvas-based dashboard charts.
- Client-side report generation for admin/auditor JSON reports.

The dashboard calls local API endpoints using `fetch`.

## Role Model

The MVP role model is implemented in dashboard JavaScript as a client-side permission map. It is useful for demo and workflow design, but it is not production authorization.

### Applicant

Allowed sections:

- Overview
- Documents
- Land
- Forecast
- Finance
- Crisis

Applicant privileges:

- Own profile
- Document submission
- Land declaration
- Crop forecast
- Crisis evidence submission
- Techno-economic analysis

### Admin

Allowed sections:

- Overview
- Applicants
- Documents
- Land
- Forecast
- Audit
- Finance
- Crisis
- Reports

Admin privileges:

- All applicants
- Role management
- Load balancing
- Audit override
- Financial review
- Reports

Admin-specific UI:

- Applicants page
- Applicant counts
- Service-window counts
- Load-balancing recommendations
- Role-management table

### Auditor

Allowed sections:

- Overview
- Documents
- Finance

Auditor privileges:

- Document review
- Economic analysis
- Payment exposure review

Auditor-specific UI:

- Applicant document objects with audit mode and risk.
- Economic-analysis objects such as yield plan, subsidy calculation, debt offset, first-sale deductions, by-product value, and market cap.

## Data Flow

1. The browser loads `/`.
2. User selects a role and signs in.
3. Browser calls `/dashboard/data`.
4. If the database is empty, demo data is initialized.
5. The response includes summary counts, applicant records, documents, subsidy claim, compensation, annual ledger, land state, crop forecast, financial analysis, audit analysis, crisis management, and audit events.
6. The dashboard renders the allowed role-specific sections.

## Reporting

Admin and auditor users can generate a local JSON report from the Reports page. The generated report includes:

- Applicant identity
- Integrity status
- Document coverage
- Audit score and findings
- Finance exposure
- Crisis incident status

This is client-side report generation for the MVP. A production system should generate reports server-side and store immutable report metadata.

## API Surface

- `GET /health`
- `GET /dashboard/data`
- `POST /applicant-screening`
- `POST /documents`
- `POST /farmers`
- `POST /parcels`
- `POST /crop-seasons`
- `POST /remote-sensing`
- `POST /first-sales`
- `POST /debts`
- `POST /subsidy-claims/calculate`
- `POST /crisis-events`
- `POST /compensation-claims/calculate`
- `GET /annual-ledger`
- `GET /audit/events`

## Production Gaps

- Server-side authentication and authorization are not implemented yet.
- Role assignments are not persisted as user accounts.
- Dashboard permissions are client-side only.
- No OpenAPI schema is generated yet.
- No end-to-end browser tests exist yet.
- SQLite is sufficient for the MVP but should become PostgreSQL/PostGIS for production.
- Audit storage is not tamper-resistant yet.
- External registry, cadastral, weather, myDATA, and payment integrations are represented as local/demo concepts.
