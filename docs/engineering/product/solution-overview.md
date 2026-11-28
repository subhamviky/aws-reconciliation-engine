# Solution overview

*One page. Synthetic data, one author.*

**The problem.** Bank statements arrive, settlements are expected, and the two rarely agree: short payments, duplicates, missing references. Matching must be exact-once and safe under retries, and every exception needs a decision with an audit trail.

**What it is.** A reconciliation engine that learns expected cash from the settlement feed, matches each bank line (exact, then oldest first, then a bounded combination), turns what it cannot match into exceptions with the nearest candidates, lets an agent propose a remedy that the rules validate twice, and posts an approved adjustment to the ledger exactly once. It runs on AWS (reference) and on Google Cloud's free tier.

**Evidence.** The cloud scenario passes against the deployed service; one defect found there (open items piling up) was fixed with a regression test and is written up as a post-incident review; messages redelivered or crashed mid-line are processed once (moto and emulator tests). Design: `docs/design/`; decisions: [ADRs](../adr/README.md).

**Limits.** One tenant per deployment; `duplicate_of` reads all lines of a tenant; the AWS stack was never applied to a real account; no load test.
