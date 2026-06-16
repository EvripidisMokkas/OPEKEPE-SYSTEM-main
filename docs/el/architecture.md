# Αρχιτεκτονική

Το OPEKEPE System είναι ένα τοπικό Python MVP με HTTP server χωρίς εξωτερικές εξαρτήσεις, SQLite persistence, browser dashboard και JSON API routes. Η υλοποίηση δίνει προτεραιότητα στη φορητότητα και στη σαφήνεια του demo αντί για production framework πολυπλοκότητα.

English version: [docs/architecture.md](../architecture.md)

Το προϊόν στον browser εμφανίζεται με την επωνυμία **OPEKEPE**. Εσωτερικά Python ονόματα όπως `agropekepe`, `AgroLedgerService` και `agroledger.sqlite3` παραμένουν για συμβατότητα με υπάρχουσες εντολές και tests.

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

## Κύρια Components

- `app.py`
  - Ορίζει το `AgroLedgerAPI`.
  - Σερβίρει το browser dashboard στο `/`.
  - Σερβίρει JSON endpoints όπως `/dashboard/data`, `/documents`, `/audit/events` και `/annual-ledger`.
  - Περιέχει το τρέχον inline HTML/CSS/JavaScript dashboard template.

- `cli.py`
  - Παρέχει εντολές `init-db`, demo setup και `serve`.

- `services.py`
  - Συντονίζει εγγραφή παραγωγού, καταχώρηση αγροτεμαχίου, ένταξη παραγωγής, πρώτες πωλήσεις, οφειλές, υπολογισμούς ενισχύσεων, περιστατικά κρίσης και ροές αποζημίωσης.

- `repository.py`
  - Διαχειρίζεται SQLite persistence και καταγραφή audit events.

- `eligibility.py`
  - Φορτώνει CAP-style κανόνες και υπολογίζει επιλεξιμότητα ενισχύσεων.

- `integrations.py`
  - Περιέχει adapter-style helpers για χάρτες, καιρό και remote-sensing concepts.

## Αρχιτεκτονική Dashboard

Το dashboard είναι προς το παρόν ένα ενιαίο inline HTML document μέσα στο `app.py`. Περιέχει:

- OPEKEPE branding.
- Οπτικό ύφος εμπνευσμένο από Python/Django.
- Επιλογέα γλώσσας `EL / EN` κάτω αριστερά.
- Επιλογέα ρόλου κατά τη σύνδεση.
- Client-side πλοήγηση με βάση τον ρόλο.
- Canvas-based charts.
- Client-side δημιουργία JSON reports για admin/auditor.

Το dashboard καλεί τα τοπικά API endpoints με `fetch`.

## Μοντέλο Ρόλων

Το MVP role model υλοποιείται σε JavaScript του dashboard ως client-side permission map. Είναι χρήσιμο για demo και σχεδιασμό workflows, αλλά δεν αποτελεί production authorization.

### Applicant

Επιτρεπόμενες ενότητες:

- Overview
- Documents
- Land
- Forecast
- Finance
- Crisis

Δικαιώματα applicant:

- Προσωπικό προφίλ
- Υποβολή εγγράφων
- Δήλωση γης
- Πρόβλεψη καλλιέργειας
- Υποβολή τεκμηρίων κρίσης
- Τεχνοοικονομική ανάλυση

### Admin

Επιτρεπόμενες ενότητες:

- Overview
- Applicants
- Documents
- Land
- Forecast
- Audit
- Finance
- Crisis
- Reports

Δικαιώματα admin:

- Όλοι οι αιτούντες
- Διαχείριση ρόλων
- Κατανομή φόρτου
- Audit override
- Οικονομικός έλεγχος
- Αναφορές

Admin-specific UI:

- Σελίδα Applicants
- Μετρήσεις αιτούντων
- Μετρήσεις service windows
- Συστάσεις κατανομής φόρτου
- Πίνακας role-management

### Auditor

Επιτρεπόμενες ενότητες:

- Overview
- Documents
- Finance

Δικαιώματα auditor:

- Έλεγχος εγγράφων
- Οικονομική ανάλυση
- Έλεγχος έκθεσης πληρωμών

Auditor-specific UI:

- Αντικείμενα εγγράφων αιτούντων με audit mode και ρίσκο.
- Αντικείμενα οικονομικής ανάλυσης όπως σχέδιο απόδοσης, υπολογισμός ενίσχυσης, συμψηφισμός οφειλής, κρατήσεις πρώτης πώλησης, αξία υποπροϊόντων και όριο αγοράς.

## Ροή Δεδομένων

1. Ο browser φορτώνει το `/`.
2. Ο χρήστης επιλέγει ρόλο και συνδέεται.
3. Ο browser καλεί το `/dashboard/data`.
4. Αν η βάση είναι άδεια, αρχικοποιούνται demo data.
5. Η απάντηση περιλαμβάνει summary counts, applicant records, documents, subsidy claim, compensation, annual ledger, land state, crop forecast, financial analysis, audit analysis, crisis management και audit events.
6. Το dashboard εμφανίζει τις ενότητες που επιτρέπονται για τον επιλεγμένο ρόλο.

## Αναφορές

Οι admin και auditor χρήστες μπορούν να δημιουργήσουν τοπικό JSON report από τη σελίδα Reports. Η αναφορά περιλαμβάνει:

- Ταυτότητα αιτούντα
- Κατάσταση ακεραιότητας
- Κάλυψη εγγράφων
- Audit score και ευρήματα
- Οικονομική έκθεση
- Κατάσταση περιστατικού κρίσης

Αυτό είναι client-side report generation για το MVP. Σε παραγωγικό σύστημα, οι αναφορές πρέπει να παράγονται server-side και να αποθηκεύουν immutable metadata.

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

- Δεν έχει υλοποιηθεί ακόμη server-side authentication και authorization.
- Οι αναθέσεις ρόλων δεν αποθηκεύονται ως λογαριασμοί χρηστών.
- Τα δικαιώματα του dashboard είναι μόνο client-side.
- Δεν παράγεται ακόμη OpenAPI schema.
- Δεν υπάρχουν ακόμη end-to-end browser tests.
- Η SQLite είναι επαρκής για το MVP, αλλά για παραγωγή πρέπει να μετακινηθεί σε PostgreSQL/PostGIS.
- Η αποθήκευση audit δεν είναι ακόμη ανθεκτική σε αλλοιώσεις.
- Διασυνδέσεις με μητρώα, κτηματολόγιο, καιρό, myDATA και πληρωμές εκπροσωπούνται ως τοπικές/demo έννοιες.
