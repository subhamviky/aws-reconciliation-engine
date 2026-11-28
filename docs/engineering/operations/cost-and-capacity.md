# Cost and capacity: reconciliation-service

Free tier ([platform note](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/cost-and-capacity.md)). Resources on Google Cloud: a Cloud Run service (scale to zero, never public), Firestore collections in the one free database, Pub/Sub topic `recon-bank-lines` with a push subscription and a dead-letter topic, one Cloud Scheduler job (`recon-scheduled`; the landscape uses all three free jobs), three service accounts. The AWS reference (Lambda, DynamoDB, SQS, EventBridge) has never been applied to a real account, so it has no cost here.

What breaks first: a transaction's item limit in one match; `duplicate_of` reading every line of a tenant (G-5); Firestore's daily free quota under a load test (none run). Measured: nothing under load.
