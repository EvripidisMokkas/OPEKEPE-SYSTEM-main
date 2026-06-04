# AgroLedger Greece — transparent agricultural subsidies management blueprint

AgroLedger Greece is a clean-room blueprint and starter implementation for a modern agricultural records, land-measurement, subsidy, tax, debt, and crisis-compensation platform inspired by the operational failures reported around the legacy Greek OPEKEPE environment.

The goal is to make every subsidy decision explainable, geospatially verifiable, auditable, and reconciled against production and financial records.

## Core principles

1. **One verified farmer identity** per beneficiary, connected to tax identity, banking, and beneficial ownership records.
2. **One canonical land parcel ledger** with ownership, leases, measurements, geometry, crop labels, and historical versions.
3. **Remote-sensing first controls** using Google Earth Engine, Sentinel/Landsat imagery, weather events, and anomaly detection before payment.
4. **Production-linked declarations** that label each hectare with crop, livestock, or ecological use per year.
5. **Financial reconciliation** between declared production, first-sale invoices, taxes, subsidies, losses, debt restructuring, and compensation.
6. **Explainable CAP payments** where every hectare, crop type, eligibility rule, and deduction is traceable.
7. **Crisis automation** for drought, flood, fire, frost, disease, or market-shock events using geofenced weather and government declarations.
8. **Anti-fraud by design** through public-land conflict checks, duplicate claims, satellite inconsistency checks, audit trails, and risk-scored payments.

## Repository contents

- [`docs/product_blueprint.md`](docs/product_blueprint.md) — product scope, data domains, workflows, controls, and rollout plan.
- [`docs/architecture.md`](docs/architecture.md) — system architecture, APIs, data pipelines, security, auditability, and integration model.
- [`schemas/agro_subsidy_core.sql`](schemas/agro_subsidy_core.sql) — starter PostGIS relational schema for farmers, parcels, crop seasons, sales, subsidies, taxes, debts, and crisis compensation.
- [`configs/cap_rules.example.json`](configs/cap_rules.example.json) — example configurable CAP payment rates and crisis policy rules.
- [`src/agropekepe/eligibility.py`](src/agropekepe/eligibility.py) — deterministic eligibility/payment engine used by the application.
- [`src/agropekepe/services.py`](src/agropekepe/services.py) — application service layer connecting farmer, land, production, finance, subsidy, debt, and crisis workflows.
- [`src/agropekepe/app.py`](src/agropekepe/app.py) — dependency-free JSON HTTP API for local use and integration tests.
- [`src/agropekepe/cli.py`](src/agropekepe/cli.py) — database initialization, demo data, and API server commands.
- [`src/agropekepe/integrations.py`](src/agropekepe/integrations.py) — Google Maps/Earth Engine and weather evidence adapter contracts.
- [`docs/task_breakdown.md`](docs/task_breakdown.md) — implementation tracks and next production tasks.
- [`tests/test_eligibility.py`](tests/test_eligibility.py), [`tests/test_services.py`](tests/test_services.py), and [`tests/test_api.py`](tests/test_api.py) — unit and API-route tests.

## Authoritative policy and platform references used

- [OPEKEPE](https://www.opekepe.gr/en/opekepe-organisation-en/106-opekepe-organisation-en) describes itself as Greece's paying and control agency for CAP aid schemes and EU agricultural funds.
- The [European Commission CAP overview](https://agriculture.ec.europa.eu/common-agricultural-policy/cap-overview/cap-2023-27_ga) explains that CAP 2023-2027 support includes direct income support, rural development, and market measures.
- The European Commission's [direct-payment eligibility overview](https://agriculture.ec.europa.eu/system/files/2024-01/direct-payments-eligibility-conditions_en.pdf) states that CAP direct payments are generally granted on a per-hectare basis subject to eligibility conditions and national strategic plans.
- [Google Earth Engine](https://cloud.google.com/earth-engine) provides cloud processing for satellite imagery and geospatial datasets; [Google Maps Platform](https://developers.google.com/maps/documentation/javascript) provides map display and geocoding services.
- [AADE myDATA](https://www.aade.gr/mydata-ilektronika-biblia) is Greece's digital accounting application and should be treated as the canonical integration target for invoice/tax reconciliation.

## Launch from Windows Terminal or VS Code Terminal

Use these commands in PowerShell, not Git Bash. Open a terminal in the project folder, or run:

```powershell
cd C:\Users\user\Documents\OPEKEPE-SYSTEM-main
```

Check Python and install the local package:

```powershell
py --version
py -m pip install -e .
```

Run the test suite:

```powershell
$env:PYTHONPATH = "src"
py -m unittest discover -s tests
```

Create the SQLite database:

```powershell
$env:PYTHONPATH = "src"
py -m agropekepe.cli --database .\agroledger.sqlite3 init-db
```

Optional: create and print a full demo record:

```powershell
$env:PYTHONPATH = "src"
py -m agropekepe.cli --database .\agroledger-demo.sqlite3 demo
```

Start the app:

```powershell
$env:PYTHONPATH = "src"
py -m agropekepe.cli --database .\agroledger.sqlite3 serve --host 127.0.0.1 --port 8080
```

Leave that terminal running. Then open this URL in your browser:

```text
http://127.0.0.1:8080/
```

Useful health check from a second PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

The browser portal is available at `/`, and JSON API routes include `/health`, `/dashboard/data`, `/farmers`, `/parcels`, `/crop-seasons`, `/subsidy-claims/calculate`, and `/annual-ledger`.

After installing the package with `py -m pip install -e .`, this shorter command also works:

```powershell
agroledger --database .\agroledger.sqlite3 serve --host 127.0.0.1 --port 8080
```

If you are running from inside a Docker container, use `--host 0.0.0.0` instead of `--host 127.0.0.1` and publish container port `8080` to your host.

## Application capabilities

The current code is now more than a static blueprint: it is a runnable local application with SQLite persistence, an application service layer, JSON HTTP routes, a CLI demo workflow, and tests. It supports farmer registration, parcel measurement from GeoJSON, annual crop enrolment per hectare, Google Maps/Earth Engine evidence adapter contracts, first-sale tax records, subsidy calculation, debt offsets, crisis declarations, compensation decisions, annual ledgers, and audit events.

## MVP build sequence

1. Implement farmer identity and parcel registry.
2. Add parcel geometry capture, cadastral/public-land conflict detection, and satellite evidence snapshots.
3. Connect declarations to crop seasons and production labels per hectare.
4. Add first-sale invoice and tax reconciliation.
5. Run deterministic subsidy calculation and payment holds before bank disbursement.
6. Add weather/crisis geofencing and compensation workflows.
7. Publish beneficiary transparency and audit dashboards.
