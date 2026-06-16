# Product Blueprint

OPEKEPE System is a local MVP for a role-based agricultural subsidy, audit, crisis-compensation, and techno-economic review platform. It demonstrates how applicants, administrators, and auditors can work from the same applicant record while seeing workflows tailored to their permissions.

Greek version: [docs/el/product_blueprint.md](el/product_blueprint.md)

## Product Goals

- Provide a clear OPEKEPE-branded workspace for agricultural support workflows.
- Connect applicant identity, land declaration, documents, crop plans, financial evidence, subsidy calculations, crisis evidence, and audit history.
- Give applicants practical estimates for expected subsidy, owed-back offsets, crop market cap, by-product value, and government coverage after crisis incidents.
- Give admins an operational view of applicants, service windows, workload queues, and role privileges.
- Give auditors a focused review view of applicant documents and related economic-analysis objects.

## User Roles

### Applicant

Applicant workflows:

- Register or sign in as an applicant.
- Review the personal application overview.
- Upload required documents and crisis evidence.
- Declare land using map, KML, and GeoJSON-oriented workflows.
- Review crop forecast and techno-economic analysis.
- Review expected subsidy, offsets, disbursable support, product income, by-product income, and market cap.
- Submit evidence for weather or other crop-damage events.
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
- Inspect applicant totals, document counts, audit events, economic records, and crisis cases.
- Monitor service-window status and queue load.
- Review load-balancing recommendations for intake, documents, audit, economic analysis, crisis incidents, and reports.
- Access every dashboard page.
- Inspect role-management configuration.
- Produce JSON reports.

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

- Review applicant document objects.
- Inspect document audit mode, file name, and risk.
- Review related economic-analysis objects.
- Compare yield plan, subsidy, debt offsets, first-sale deductions, by-product value, and market cap.

Auditor pages:

- Overview
- Documents
- Finance

## Dashboard Experience

The dashboard includes:

- OPEKEPE visible branding.
- Python/Django-inspired styling.
- Fixed bottom-left `EL / EN` language selector.
- Role selector at sign-in.
- Permission-gated navigation.
- Role-specific cards, tables, and charts.
- Canvas charts for finance, crop forecast, crisis, and audit confidence.

## Core Workflows

### Applicant Screening

Applicant registration checks public-integrity exposure and local disclosure matches. The screening result routes the applicant into either:

- `off_the_hook`
- `enhanced_audit`

Document audit mode is then set as:

- `standard_audit`
- `close_audit`

### Documents

Required document categories:

- Identity or tax certificate
- Land title, lease, or cadastral extract
- Financial records and invoices
- IBAN proof
- Crisis incident evidence

Submitted documents receive risk and audit metadata.

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

Applicants can submit evidence for crop damage caused by weather or other conditions. The MVP models evidence such as:

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

The crisis page estimates gross crisis payment, exposed property value, destruction loss, collective revenue loss, net subsidy after offsets, and review status.

### Admin Operations

The admin Applicants page provides:

- All-applicants table
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

- The system is a local demo.
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
