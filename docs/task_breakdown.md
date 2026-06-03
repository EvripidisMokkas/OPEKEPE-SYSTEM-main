# Implementation task breakdown

This repository now contains a dependency-free MVP application that can be extended into a production agricultural subsidies system. The work is split into separate implementation tracks so teams can build and review independently.

## Track 1: Farmer identity and access

- Current code: farmer registration with tax identifier, legal name, type, active-farmer status, persistence, and audit events.
- Next production tasks:
  - Connect to government identity providers.
  - Add bank-account verification and beneficial-ownership checks.
  - Add delegated access for accountants, cooperatives, agronomists, and family representatives.

## Track 2: Land registry and measurement

- Current code: parcel registration from GeoJSON, approximate hectare measurement, centroid calculation, rights type, public/protected-land conflict flags, persistence, and audit events.
- Next production tasks:
  - Replace approximate geometry calculations with PostGIS/geodetic measurement services.
  - Integrate national cadastral/public-land/protected-area overlays.
  - Add parcel versioning and overlap resolution workflows.

## Track 3: Google Maps and Earth Engine evidence

- Current code: deterministic Google Maps parcel links and normalized Google Earth Engine crop/weather observation adapters.
- Next production tasks:
  - Add authenticated Google Maps Platform parcel editing UI.
  - Add Earth Engine jobs for NDVI/EVI, crop classification, boundary changes, flood, drought, burn, and frost signals.
  - Store imagery snapshots and model versions in immutable evidence storage.

## Track 4: Production enrolment per hectare

- Current code: crop season enrolment per parcel, claim year, production type, labelled hectares, irrigation status, organic/soil-cover flags, declared and verified yields, and crop-label confidence.
- Next production tasks:
  - Support sub-parcel geometries for multiple crops on one cadastral parcel.
  - Add livestock/pasture stocking-density checks.
  - Add agronomist review queues for low-confidence labels.

## Track 5: First-sale finance and tax records

- Current code: first-sale invoice records, buyer tax identifier, product type, quantity, price, tax rate, myDATA mark, gross/net/tax calculation, and annual ledger aggregation.
- Next production tasks:
  - Integrate AADE myDATA invoice ingestion.
  - Add cooperative settlement notes and transport documents.
  - Add product transformation records after the first-sale taxable event.

## Track 6: Subsidy eligibility and debt management

- Current code: configurable per-hectare rates, eco bonuses, public-land holds, crop-confidence holds, yield-variance holds, debt offset calculations, annual subsidy claim totals, and risk flags.
- Next production tasks:
  - Encode official CAP strategic-plan schemes as versioned rule sets.
  - Add payment batches, recoveries, appeals, and four-eyes approval.
  - Add sanctions, ceilings, redistributive payments, coupled support, and eco-scheme evidence checks.

## Track 7: Crisis and compensation management

- Current code: geofenced crisis events, weather/satellite evidence requirements, affected-hectare calculation, damage percentage checks, annual caps, and explainable compensation decisions.
- Next production tasks:
  - Integrate official disaster declarations and real-time weather feeds.
  - Add insurance and prior-compensation reconciliation.
  - Add emergency advances, final settlements, clawbacks, and appeals.

## Track 8: Audit, transparency, and reporting

- Current code: append-only SQLite audit events and annual farmer ledger view combining production, first sales, taxes, subsidies, debt, net support, and risk flags.
- Next production tasks:
  - Move audit events to tamper-resistant/WORM storage.
  - Build public CAP transparency publication filters.
  - Add regional dashboards, risk heatmaps, and auditor search tools.

## Track 9: API and operations

- Current code: dependency-free JSON HTTP API with routes for farmers, parcels, crop seasons, remote-sensing evidence, sales, debts, subsidy calculation, crisis events, compensation, annual ledger, audit events, and health checks.
- Next production tasks:
  - Replace the stdlib HTTP server with a hardened web framework if desired.
  - Add authentication, authorization, rate limiting, validation schemas, and OpenAPI documentation.
  - Deploy with PostgreSQL/PostGIS, object storage, background jobs, and event queues.
