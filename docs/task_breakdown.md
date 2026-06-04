# Ανάλυση εργασιών υλοποίησης

Το αποθετήριο περιέχει MVP χωρίς εξωτερικές εξαρτήσεις, με ελληνική διεπαφή ως πρώτη έκδοση και επιλογή αγγλικής εναλλακτικής προβολής.

## Ενότητα 1: Ταυτότητα και πρόσβαση

- Υλοποιημένο: σύνδεση, ξεχωριστή εγγραφή, ΑΦΜ/κωδικός, έλεγχος δημόσιας ακεραιότητας, `off_the_hook`, `enhanced_audit`.
- Επόμενα: πραγματική ταυτοποίηση, hashing κωδικών, sessions, ανάκτηση λογαριασμού, εξουσιοδοτημένη πρόσβαση λογιστών και συνεταιρισμών.

## Ενότητα 2: Αγροτεμάχια και μέτρηση

- Υλοποιημένο: GeoJSON, εκτίμηση εκταρίων, centroid, τύπος δικαιώματος, flags δημόσιας/προστατευόμενης γης.
- Επόμενα: PostGIS, Κτηματολόγιο, δημόσιες εκτάσεις, versioning και επίλυση overlaps.

## Ενότητα 3: Χάρτες και τηλεπισκόπηση

- Υλοποιημένο: Google Maps links, Earth Engine adapter contracts, καιρός εντός πρόβλεψης καλλιέργειας.
- Επόμενα: πραγματικό map editing, NDVI/EVI, ταξινόμηση καλλιεργειών, ζημιές από πλημμύρα/ξηρασία/πυρκαγιά.

## Ενότητα 4: Παραγωγή ανά εκτάριο

- Υλοποιημένο: καλλιεργητικές περίοδοι, τύπος παραγωγής, δηλωμένη/επαληθευμένη απόδοση, confidence.
- Επόμενα: υπο-αγροτεμάχια, κτηνοτροφικοί έλεγχοι, queues γεωπόνων.

## Ενότητα 5: Οικονομικά, προϊόντα και υποπροϊόντα

- Υλοποιημένο: πρώτη πώληση, φόρος, market cap, τιμές προϊόντων/υποπροϊόντων, έσοδα, γραφήματα.
- Επόμενα: AADE myDATA, συνεταιριστικές εκκαθαρίσεις, επίσημες αγοραίες τιμές και benchmark tables.

## Ενότητα 6: Ενισχύσεις και οφειλές

- Υλοποιημένο: κανόνες ανά εκτάριο, eco bonuses, holds, συμψηφισμός οφειλών, risk flags.
- Επόμενα: πλήρη CAP schemes, batches πληρωμών, appeals, κυρώσεις και four-eyes approval.

## Ενότητα 7: Κρίσεις και αποζημιώσεις

- Υλοποιημένο: γεωφραγμένα συμβάντα, ζημιές, annual cap, ακαθάριστη αποζημίωση και crisis graphs.
- Επόμενα: επίσημες δηλώσεις καταστροφών, ασφαλιστικά στοιχεία, προκαταβολές, τελικές εκκαθαρίσεις και ενστάσεις.

## Ενότητα 8: Έλεγχος και αναφορές

- Υλοποιημένο: audit events, προβολή standard/close audit, applicant review actions, annual ledger.
- Επόμενα: WORM storage, public transparency filters, risk heatmaps και case management.

## Ενότητα 9: API και λειτουργία

- Υλοποιημένο: JSON API για health, dashboard, applicant screening, documents, farmers, parcels, crop seasons, claims, crises και annual ledger.
- Επόμενα: authentication, authorization, validation schemas, rate limiting και OpenAPI.

## Ενότητα 10: Πύλη browser

- Υλοποιημένο: ελληνική πρώτη έκδοση, επιλογέας `EL / EN`, login/register, dashboard tabs, forecast, financial graphs και crisis views.
- Επόμενα: accessibility review, mobile testing, persistent accounts και end-to-end UI tests.
