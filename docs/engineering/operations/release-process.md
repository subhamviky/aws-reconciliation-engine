# Release process: reconciliation-service

Platform workflows: [release process](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/operations/release-process.md). For this repository:

1. Branch and pull request. CI (`reconciliation-ci`): unit, flow, Lambda and contract tests with DynamoDB and SQS mocked by moto; strict E2A conformance; the Firestore emulator pass (every test with `RECON_STATE_BACKEND=firestore`); a check that the vendored settlement contract equals the producer's `main`; Terraform fmt, validate and test with a mock provider; the AWS stack is applied to a moto server, smoke-tested through the real Lambda handler, and destroyed.
2. Merge to `main`: a release is a commit and a Cloud Run revision (no version number).
3. Deploy: Actions, `ops` (assistant repository), `deploy`, service `reconciliation-service`, ref `main`. No canary for this service.
4. Verify: `landscape-gcp` on `main` (the scenario reads exceptions and lines, closes an exception, and checks the open item).
5. Rollback: `gcloud run services update-traffic reconciliation-service --region us-central1 --to-revisions <previous>=100`. Data written under the new revision stays; the conditional writes keep both revisions safe.

A change to the settlement contract needs the vendored copy updated in the same pull request.
