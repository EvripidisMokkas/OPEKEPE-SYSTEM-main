# Product blueprint: AgroLedger Greece

## 1. Problem statement

The legacy subsidy workflow must be replaced with a system where land, production, financial records, subsidy claims, taxes, losses, and crisis compensation are connected in one auditable ledger. The product should prevent false parcel ownership or lease declarations, duplicate hectare claims, implausible production claims, and payments unsupported by remote-sensing or financial evidence.

## 2. Policy assumptions

This blueprint should be implemented as a configurable rules platform rather than hard-coding subsidy law. CAP rates, eligible hectares, eco-scheme conditions, coupled support, redistributive payments, payment ceilings, crisis-compensation rates, tax rules, and debt relief rules change by year and must be configured by authorized policy administrators.

The platform treats the following as first-class compliance obligations:

- Paying-agency controls and audit evidence for EU funds.
- Per-hectare eligibility calculations by calendar or claim year.
- Public transparency for CAP beneficiaries where legally required.
- Privacy, data-minimization, and role-based access controls for personal, tax, and banking data.
- Explainable payment decisions, holds, reductions, recoveries, and appeals.

## 3. User groups

| User group | Main responsibilities |
| --- | --- |
| Farmer / cooperative | Registers identity, land, crops, production, invoices, insurance, and claims. |
| Surveyor / agronomist | Verifies parcel boundaries, crop labels, yield plausibility, and damage reports. |
| Paying agency officer | Reviews eligibility, controls, payment batches, recoveries, and appeals. |
| Tax authority | Reconciles first-sale invoices, taxable events, VAT/income-tax treatment, and reported production. |
| Crisis-management authority | Opens crisis events, geofences affected areas, sets compensation rules, and approves emergency support. |
| Auditor / prosecutor | Reviews immutable records, evidence chain, payment rationale, anomalies, and conflict-of-interest signals. |
| Public transparency user | Sees legally publishable beneficiaries, regions, measures, and amounts. |

## 4. Core data domains

### 4.1 Farmer and beneficiary identity

- Legal identity, tax identifier, social-security/agricultural registry identifier, cooperative membership, bank account, beneficial ownership, sanctions screening, and role delegations.
- Annual active-farmer status, farm size, young-farmer status, small-farmer status, and other configurable CAP attributes.
- Consent and authorization records for integrations with cadastral, tax, banking, satellite, and weather systems.

### 4.2 Land records and measurement

- Cadastral parcel references, ownership or lease evidence, public-land status, protected-area overlays, Natura/forest/coastal restrictions, irrigation access, and soil attributes.
- GIS geometry stored as versioned polygons with declared area, measured area, eligible area, and excluded ineligible features.
- Measurement evidence from surveyor uploads, mobile GPS traces, orthophotos, Google Maps display, and Earth Engine-derived satellite observations.

### 4.3 Production enrolment and hectare labels

- Each annual crop season links a parcel or sub-parcel area to production type, crop variety, livestock/pasture use, organic status, irrigation method, sowing date, harvest window, expected yield, and declared yield.
- Crop labels are versioned so corrections do not erase previous declarations.
- Remote-sensing classification produces confidence scores and highlights disagreements between declared and observed use.

### 4.4 Financial records and taxes

- First round of sale records connect products to invoices, buyers, quantities, prices, VAT, taxes withheld, cooperative settlement notes, and transport documents.
- Product transformation or transfer to another industry is recorded after the first-sale taxable event.
- Revenue per hectare and yield per hectare are compared to regional norms to detect under-reporting, over-reporting, or subsidy-only farming patterns.

### 4.5 Subsidies and payment entitlements

- Subsidy claims are calculated by year, farmer, parcel, eligible hectares, production type, scheme, and rule version.
- The engine records base amount, eco-scheme amount, coupled support, redistributive support, reductions, penalties, holds, recoveries, and final disbursement.
- Every line item stores the exact rule, input facts, evidence links, reviewer actions, and appeal state.

### 4.6 Debt, loss, and crisis management

- Debt records include tax debt, social-security debt, bank debt, cooperative debt, recovery orders, and restructuring plans.
- Loss events can be farmer-reported, weather-triggered, satellite-triggered, or government-declared.
- Crisis compensation is calculated from affected hectares, production type, damage percentage, uninsured/insured status, previous subsidies, previous compensation, and annual caps.

## 5. End-to-end annual workflow

1. **Pre-season registry refresh**: verify identity, active-farmer status, bank account, cadastral rights, leases, public-land conflicts, and previous recoveries.
2. **Parcel declaration**: farmer draws or confirms parcel boundaries on a map; the system computes measured area, overlap conflicts, and eligible area.
3. **Production declaration**: farmer labels each hectare with crop, pasture, livestock, fallow, ecological focus, or other use.
4. **Remote-sensing monitoring**: Earth observation jobs calculate vegetation indices, crop-classification confidence, land-use changes, burn/flood/drought indicators, and boundary anomalies.
5. **Financial declaration**: first-sale invoices and production quantities are reconciled against the declared crop season.
6. **Eligibility and risk scoring**: the engine calculates subsidies and flags high-risk claims for review before payment.
7. **Payment authorization**: low-risk claims proceed to payment; high-risk claims enter hold, inspection, correction, or appeal.
8. **Tax and debt offsets**: configured offsets are applied to debts or recovery orders before disbursement when legally permitted.
9. **Crisis events**: government geofences crisis areas, validates affected parcels, computes compensation, and publishes decisions.
10. **Transparency and audit**: publish legally required beneficiary data and preserve full immutable audit evidence.

## 6. Anti-fraud controls

| Risk | Control |
| --- | --- |
| Public land claimed as private or leased | Cadastral and public-land overlay check before claim submission. |
| Same hectare claimed by multiple beneficiaries | Geometry overlap detection and payment hold until resolved. |
| False pasture/livestock declarations | Cross-check parcel vegetation, grazing calendar, livestock registry, and stocking density. |
| Declared crop differs from actual crop | Crop classification confidence, NDVI/EVI time series, and agronomist review. |
| Subsidy without real production | Compare production declaration, invoices, yields, and first-sale tax records. |
| Inflated crisis losses | Weather-event geofence, satellite damage indicators, insurance records, and historic yield baseline. |
| Insider manipulation | Segregation of duties, immutable audit log, privileged-action alerts, and random independent review. |
| Payment to risky beneficiary | Risk-scored payment holds, recoveries, sanctions, and bank-account verification. |

## 7. Minimum viable product

### Phase 1: Registry foundation

- Farmer identity registry.
- Parcel geometry registry.
- Ownership/lease evidence upload.
- Annual production declarations.
- Deterministic subsidy calculation from configurable rates.

### Phase 2: Verification and controls

- Cadastral/public-land overlays.
- Google Maps parcel editing interface.
- Earth Engine imagery pipeline.
- Duplicate claim and overlap detection.
- Audit log and reviewer workbench.

### Phase 3: Finance, tax, and debt integration

- AADE myDATA invoice imports.
- First-sale tax event reconciliation.
- Debt registry and legal offset workflows.
- Recovery-order management.

### Phase 4: Crisis and compensation

- Weather and disaster event ingestion.
- Crisis geofence manager.
- Damage assessment and compensation calculator.
- Farmer appeal and evidence submission.

### Phase 5: Transparency and analytics

- Public beneficiary portal.
- Regional payment heatmaps.
- Fraud risk dashboards.
- CAP performance indicators.

## 8. Success metrics

- Percentage of claimed hectares with verified geometry and rights.
- Percentage of payments with complete rule/evidence traceability.
- Duplicate/overlap claim rate before and after controls.
- Average payment cycle time for low-risk claims.
- Number and value of prevented erroneous payments.
- Tax reconciliation rate for first-sale agricultural products.
- Crisis-compensation processing time from event declaration to payment.
- Appeal reversal rate and reasons.
