# OPEKEPE System

OPEKEPE System is a local Python MVP for agricultural subsidy management, audit review, crisis compensation, and techno-economic analysis. It demonstrates how applicant declarations, land evidence, crop plans, financial records, audit history, role-based access, and crisis evidence can work together in one traceable service.

The browser dashboard is branded as **OPEKEPE**. The internal Python package remains `agropekepe`, and the demo SQLite database remains `agroledger.sqlite3`, so the existing imports, commands, and tests continue to work.

## Documentation

- [Product Blueprint](docs/product_blueprint.md)
- [Architecture](docs/architecture.md)
- [Task Breakdown](docs/task_breakdown.md)
- [Greek README / Ελληνικό README](README.el.md)

## Current Features

- Local browser portal served by a dependency-free Python HTTP server.
- OPEKEPE-branded dashboard with a Python/Django-inspired interface.
- Fixed `EL / EN` language selector in the bottom-left corner.
- Role selector at sign-in for `Applicant`, `Admin`, and `Auditor` views.
- Applicant registration and public-integrity screening.
- Applicant document upload flow for identity, land, finance, bank, and crisis evidence.
- Land declaration view with Google Maps center, Google Earth KML, and GeoJSON actions.
- Crop forecast and techno-economic analysis for yield, subsidy, costs, net margin, market cap, products, and by-products.
- Applicant finance view with expected subsidy, owed-back offsets, disbursable amount, and market-flow events.
- Applicant crisis view for weather or crop-damage evidence, coverage estimates, and compensation scenarios.
- Admin applicants page with totals, service-window counts, load-balancing queues, and operational recommendations.
- Admin role-management table for configured role privileges.
- Auditor view focused on applicant documents and related economic-analysis objects.
- Reports page for admin/auditor JSON report generation.
- JSON API endpoints and unit/API tests for the service core.

## Roles

### Applicant

Applicants use the system as an operational workspace for their own case. They can review their overview, documents, land declaration, crop forecast, finance, and crisis-management pages. They can submit documents and crisis evidence, inspect expected subsidy values, see offsets owed back, review expected disbursable support, and understand crop-income and by-product projections.

### Admin

Admins can access every dashboard section: overview, applicants, documents, land declaration, crop forecast, audit analysis, finance, crisis management, and reports. They also get operational tools for applicant totals, document and audit counts, economic and crisis records, load-balancing recommendations, service-window status, and role-management visibility.

### Auditor

Auditors are intentionally limited to review-focused areas: overview, documents, and finance. The document view shows applicant document objects, file names, audit modes, and risk. The finance view shows related economic-analysis objects such as yield plan, subsidy calculation, debt offset, first-sale deductions, by-product value, and maximum market cap.

## Repository Contents

- `src/agropekepe/app.py` - JSON API and browser dashboard.
- `src/agropekepe/cli.py` - command-line entry point for database setup, demo data, and serving.
- `src/agropekepe/services.py` - application service layer.
- `src/agropekepe/repository.py` - SQLite persistence layer.
- `src/agropekepe/eligibility.py` - subsidy eligibility and payment calculation rules.
- `src/agropekepe/integrations.py` - adapter-style helpers for maps, weather, and external-service concepts.
- `configs/cap_rules.example.json` - example CAP rule configuration.
- `docs/product_blueprint.md` - English product and workflow blueprint.
- `docs/architecture.md` - English technical architecture and API notes.
- `docs/task_breakdown.md` - English implementation status and next tasks.
- `docs/el/` - Greek documentation versions.
- `tests` - unit and API tests.

## Run Locally

Open PowerShell in the project folder:

```powershell
cd C:\Users\user\Documents\OPEKEPE-SYSTEM-main
```

Check Python:

```powershell
py --version
```

Run tests:

```powershell
$env:PYTHONPATH = "src"
py -m unittest discover -s tests
```

Initialize the SQLite database:

```powershell
$env:PYTHONPATH = "src"
py -m agropekepe.cli --database .\agroledger.sqlite3 init-db
```

Start the application:

```powershell
$env:PYTHONPATH = "src"
py -m agropekepe.cli --database .\agroledger.sqlite3 serve --host 127.0.0.1 --port 8080
```

Open:

```text
http://127.0.0.1:8080/
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

## API Endpoints

- `GET /health` - service health check.
- `GET /dashboard/data` - initialized dashboard snapshot.
- `POST /applicant-screening` - applicant public-integrity screening.
- `POST /documents` - document metadata and audit analysis submission.
- `POST /farmers` - farmer/applicant creation.
- `POST /parcels` - parcel registration.
- `POST /crop-seasons` - crop-season registration.
- `POST /remote-sensing` - remote-sensing observation registration.
- `POST /first-sales` - first-sale and tax registration.
- `POST /debts` - debt registration for subsidy offsets.
- `POST /subsidy-claims/calculate` - annual subsidy calculation.
- `POST /crisis-events` - crisis incident declaration.
- `POST /compensation-claims/calculate` - crisis compensation calculation.
- `GET /annual-ledger` - annual farmer ledger.
- `GET /audit/events` - audit event list.

## MVP Boundaries

This is a local demo MVP. It does not yet include production authentication, persistent user accounts, real government registry integrations, real payment rails, or production-grade geospatial infrastructure.

Recommended next steps:

- Replace the demo role selector with authenticated user accounts and server-side authorization.
- Persist role assignments and applicant-user relationships.
- Add OpenAPI documentation.
- Add end-to-end UI tests for role-specific navigation.
- Integrate official registries, AADE/myDATA, cadastral systems, weather evidence, and payment systems.
- Move geospatial storage to PostGIS for production use.
- Add tamper-resistant audit storage.
