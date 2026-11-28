# Test strategy: reconciliation-service

Shared principles: [platform strategy](https://github.com/subhamviky/enterprise-finance-genai-assistant/blob/main/docs/engineering/testing/test-strategy.md). Layers here (82 test functions):

| Layer | What it proves |
|---|---|
| Unit | the matcher (exact, FIFO, subset-sum, nearest), duplicate detection, `validate`, the consumer's claim states (duplicate, deferred, resumed, dead-lettered) |
| Flow | a line from arrival to MATCHED or EXCEPTION; accept with re-validation and confirmation; `resolve` with an adjustment, including that it consumes the open item (the regression for review 0003) |
| Lambda and contract | `lambda_entry.handler` with SQS batches; the settlement contract |
| moto | DynamoDB and SQS mocked for the whole suite; the AWS stack applied to a moto server and smoke-tested |
| Firestore | every test again with the Firestore repository on the emulator |
| Conformance and contract drift | strict E2A conformance; the vendored settlement contract equals the producer's `main` |
| Infrastructure | Terraform fmt, validate, test with a mock provider |
| Cloud | the landscape scenario (statements, exceptions, resolve) and the drills in the assistant repository |

Gaps: no load or scale test (`duplicate_of`'s cost); the AWS stack never applied to a real account; no property-based tests of the matcher.
