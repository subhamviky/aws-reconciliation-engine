# Requirements and user stories

Business rules (BR-1 to BR-13) and use cases (UC-1 to UC-5) are traced in the design document, section 2. Stories with acceptance criteria that are tests:

| # | As a... | I want... | So that... | Acceptance |
|---|---|---|---|---|
| R1 | reconciliation analyst | bank lines matched to expected settlements automatically | I only see the exceptions | exact match, then oldest-first, then a bounded subset; every match atomic |
| R2 | analyst | a duplicate payment detected | it is not matched twice | `duplicate_of` flags it |
| R3 | analyst | exceptions with the nearest candidate settlements | I can see why it did not match | the exception lists candidates and the difference |
| R4 | analyst | a proposed action with a reason, never executed unvalidated | the model cannot do harm | validate on store and on accept; beyond-limit refused |
| R5 | analyst | accepting an exception to post one adjustment | the ledger reflects the decision | the adjustment key `recon-<tenant>-<line_id>`; a ledger outage leaves it PENDING and retried |
| R6 | other systems | to read lines and exceptions, and close an exception only on ledger evidence | no system closes on another's word | service routes with grants; `resolve` checks the ledger and consumes the open item |
| R7 | operator | redelivery, crashes and dead letters handled | I do not repair by hand | claims, resumable handler, `reconcile` |

Non-functional: private by default; one tenant per deployment; free tier. Out of scope: multi-currency matching, a user interface, multi-tenant deployments.
