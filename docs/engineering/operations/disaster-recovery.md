# Disaster recovery: reconciliation-service

Platform plan: [disaster recovery](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/disaster-recovery.md). Specific here:

State is in Firestore (GCP) or DynamoDB (AWS); there is no backup of it beyond the cloud's own durability. What can be rebuilt: open items from the settlement feed (reset the cursor and poll: the conditional puts make this idempotent), lines from the statements (re-submit them: claims make this idempotent). What cannot: exception decisions made by a person after the last re-submission. Messages wait 24 hours in Pub/Sub; the DLQ holds what failed five times.

RTO for a bad revision: roll back traffic. RPO: not defined beyond Firestore's guarantees; no export is scheduled.
