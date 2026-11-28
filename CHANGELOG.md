# Changelog

Newest first. [Keep a Changelog](https://keepachangelog.com). Released by commit and Cloud Run revision.

## 28 November 2026
### Added
- Engineering records (`docs/engineering/`).

## 27 November 2026 (GCP-02 Phase B)
### Added
- Correlation id: one JSON log line per request carrying `X-Correlation-Id`.
### Fixed
- Resolving with an adjustment consumes the settlement's open item (found by the cloud scenario: open items piled up and the current run's settlement fell out of the candidates).

## 26 November 2026 (GCP-02 Phase A)
### Added
- `POST /service/v1/exceptions/{line_id}/resolve`: close an exception only when the ledger shows the adjustment.

## 25 November 2026 (GCP-01)
### Added
- Google Cloud free-tier deployment: Cloud Run, Firestore repository, Pub/Sub push delivery, scheduled run.

## Earlier
- The completed project rebuilt from the spike on the E2A and A2C frameworks (AWS reference deployment).
