# OPEKEPE System

OPEKEPE System is a local Python MVP for agricultural subsidy, audit, crisis-compensation, and techno-economic review workflows. It provides a browser dashboard and JSON API for demonstrating how applicant declarations, land evidence, crop plans, financial records, audit history, role-based access, and crisis evidence can be connected into one traceable service.

The browser UI is branded as **OPEKEPE** and uses a Python/Django-inspired dashboard style. The internal Python package is still named `agropekepe`, and the demo SQLite database is still `agroledger.sqlite3`, so existing imports, commands, and tests remain stable.

## Current Features

- Local browser portal served by a dependency-free Python HTTP server.
- OPEKEPE-branded dashboard with Python/Django-inspired styling.
- Language selector `EL / EN`, now fixed at the bottom-left of the UI.
- Role selector at sign-in with `Applicant`, `Admin`, and `Auditor` views.
- Applicant registration and public-integrity screening.
- Applicant document upload flow for identity, land, finance, bank, and crisis evidence.
- Land declaration view with Google Maps center, Google Earth KML, and GeoJSON actions.
- Crop forecast and techno-economic analysis for expected yield, subsidy, costs, net margin, market cap, products, and by-products.
- Applicant finance view with expected subsidy, owed-back offsets, disbursable amount, and market-flow events.
- Applicant crisis incident view for weather or other crop-damage evidence, government coverage estimates, and compensation scenarios.
- Admin applicants page with total applicants, service-window counts, load-balancing queues, and operational recommendations.
- Admin role-management table for the configured role privileges.
- Auditor view scoped to applicant document objects and related economic-analysis objects.
- Reports page for admin/auditor JSON report generation.
- JSON API endpoints and unit/API tests for the service core.

## Roles

### Applicant

Applicants can see their own operational workspace:

- Overview
- Documents
- Land declaration
- Crop forecast
- Finance
- Crisis management

Applicants can submit documents and crisis evidence, inspect their expected subsidy, see subsidy offsets owed back, review expected disbursable support, and understand crop/yield market cap and by-product income.

### Admin

Admins can see every dashboard window:

- Overview
- Applicants
- Documents
- Land declaration
- Crop forecast
- Audit analysis
- Finance
- Crisis management
- Reports

Admins also get a dedicated applicants/operations page with:

- All applicants in the current system snapshot
- Total applicant count
- Document, audit, economic, and crisis record counts
- Load-balancing recommendations by operational window
- Service-window status table
- Role-management overview

### Auditor

Auditors are intentionally restricted to review surfaces:

- Overview
- Documents
- Finance

The auditor document page shows applicant document objects, audit mode, file name, and risk. The auditor finance page shows related economic-analysis objects such as declared yield plan, subsidy calculation, debt offset, first-sale deductions, by-product value, and maximum market cap.

## Repository Contents

- `src/agropekepe/app.py` - JSON API and browser dashboard.
- `src/agropekepe/cli.py` - command-line entry point for database setup, demo data, and serving.
- `src/agropekepe/services.py` - application service layer.
- `src/agropekepe/repository.py` - SQLite persistence layer.
- `src/agropekepe/eligibility.py` - subsidy eligibility and payment calculation rules.
- `src/agropekepe/integrations.py` - adapter-style helpers for maps, weather, and external-service concepts.
- `configs/cap_rules.example.json` - example CAP rule configuration.
- `docs/product_blueprint.md` - product and workflow blueprint.
- `docs/architecture.md` - technical architecture and API notes.
- `docs/task_breakdown.md` - implementation status and next tasks.
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

## Current MVP Boundaries

This is a local demo MVP. It does not yet include production authentication, persistent user accounts, real government registry integrations, real payment rails, or production-grade geospatial infrastructure.

Recommended next steps:

- Replace demo role selector with authenticated user accounts and server-side authorization.
- Persist role assignments and applicant-user relationships.
- Add OpenAPI documentation.
- Add end-to-end UI tests for role-specific navigation.
- Integrate official registries, AADE/myDATA, cadastral systems, weather evidence, and payment systems.
- Move geospatial storage to PostGIS for production use.
- Add tamper-resistant/WORM audit storage.
