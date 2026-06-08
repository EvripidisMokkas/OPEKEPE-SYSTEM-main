# Product Blueprint

OPEKEPE System is an MVP for a role-based agricultural subsidy and crisis-compensation platform. It demonstrates how applicants, admins, and auditors can interact with the same underlying applicant record while seeing different workflows based on privileges.

## Product Goals

- Provide a clear OPEKEPE-branded dashboard for agricultural support workflows.
- Connect applicant identity, land declaration, documents, crop plans, financial evidence, subsidy calculations, crisis evidence, and audit history.
- Give applicants practical estimates of expected subsidy, owed-back offsets, crop market cap, by-products, and government coverage after crisis incidents.
- Give admins an operational view of all applicants, service windows, and workload balancing.
- Give auditors a focused review view of applicant documents and related economic-analysis objects.

## User Roles

### Applicant

Applicant workflows:

- Register or sign in as applicant.
- View own application overview.
- Upload required documents.
- Declare land through map/KML/GeoJSON-oriented workflows.
- Review crop forecast and techno-economic analysis.
- Review finance page with expected subsidy, offsets, disbursable amount, product income, by-product income, and market cap.
- Submit crisis evidence for weather or other crop-damage events.
- Review government coverage and compensation estimates.

Applicant pages:

- Overview
- Documents
- Land
- Forecast
- Finance
- Crisis

### Admin

Admin workflows:

- View all applicants in the current system snapshot.
- See total applicants, document count, audit events, economic record count, and crisis cases.
- Inspect service-window status.
- Review load-balancing recommendations for intake, documents, audit, economic analysis, crisis incidents, and reports.
- Access every dashboard page.
- Inspect role-management configuration.
- Produce reports.

Admin pages:

- Overview
- Applicants
- Documents
- Land
- Forecast
- Audit
- Finance
- Crisis
- Reports

### Auditor

Auditor workflows:

- Review applicant documents.
- Inspect document audit modes and risks.
- Review related economic-analysis objects only.
- Compare yield plan, subsidy, debt offsets, first-sale deductions, by-product value, and market cap.

Auditor pages:

- Overview
- Documents
- Finance

## Dashboard Experience

The dashboard uses:

- OPEKEPE name in the visible UI.
- Python/Django-inspired visual style.
- Fixed bottom-left language selector.
- Role selector at sign-in.
- Permission-gated navigation.
- Role-specific cards and tables.
- Canvas charts for finance, crop forecast, crisis, and audit confidence.

## Core Workflows

### Applicant Screening

Applicant registration checks public-integrity exposure and local disclosure matches. The result routes the applicant into either:

- `off_the_hook`
- `enhanced_audit`

Document audit mode is then set as:

- `standard_audit`
- `close_audit`

### Documents

Required document categories:

- Identity/tax certificate
- Land title, lease, or cadastral extract
- Financial records and invoices
- IBAN proof
- Crisis incident evidence

Documents receive risk and audit metadata when submitted.

### Crop Forecast And Finance

The system estimates:

- Forecast yield
- Maximum benchmark yield
- Gross crop income
- By-product income
- Input and field costs
- Subsidy
- Debt offset
- Disbursable support
- Net margin
- Market cap at maximum yield
- Market-flow events

### Crisis Incident

Applicants can submit evidence for crop damage caused by weather or other conditions. The current MVP models evidence such as:

- Rainfall deficit
- Flood trace
- Frost
- Wind
- Fire perimeter
- Crop-damage photos
- Agronomist note
- Field inspection
- Yield reduction
- First sales and invoices
- Repair costs
- Lost production value

The crisis page estimates:

- Gross crisis payment
- Property value exposed
- Property destruction loss
- Collective revenue loss
- Net subsidy after offsets
- Review status

### Admin Operations

The admin Applicants page provides:

- All applicants table
- Applicant totals
- Operational queue counts
- Service-window view
- Load-balancing recommendations
- Quick navigation into review windows

### Reports

Admin and auditor users can produce a local JSON report containing:

- Applicant identity
- Integrity status
- Document state
- Audit findings
- Finance exposure
- Crisis status

## MVP Constraints

- This is a local demo.
- Role permissions are currently client-side.
- User accounts are not persisted.
- Reports are generated client-side.
- External integrations are simulated or represented as local concepts.

## Product Next Steps

- Add real authentication and persisted users.
- Move role permissions server-side.
- Persist role assignments and applicant ownership.
- Add admin assignment workflows for auditors.
- Add report persistence and approval state.
- Add OpenAPI documentation.
- Add end-to-end role tests.
- Integrate official government registries and payment systems.
