# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [SemVer](https://semver.org/).

## [0.1.0] - 2026-09-08

Initial beta. Public contract mirrors [zkp-sdk-php](https://github.com/zerokyc-payments/zkp-sdk-php).

### Added
- `ZeroKYC` facade: `create_invoice()`, `get_invoice()`, `cancel_invoice()`, `ping()`, `verify_webhook()`.
- Typed invoice models with normalized `InvoiceStatus` enum
  (PENDING / CONFIRMING / PAID / UNDERPAID / EXPIRED / CANCELLED / OVERPAID / FAILED).
- `WebhookVerifier`: strict `t=...,v1=...` header parsing, ±300 s replay window,
  HMAC-SHA256 with constant-time comparison; handles both the production payload
  shape (invoice id and paid asset nested in `data.option`) and the docs test vector.
- `ReplayGuard` + `EventStore` protocol: `is_duplicate()` is a pure check;
  `mark_processed()` is called only after the local order update succeeds.
  Payment matching (invoice / amount / asset, ticker or asset-id spellings).
- `idempotency_key()` helper (`zerokyc:{platform}:{entity}:{id}`, max 120 chars).
- Sandbox/production configuration with key/environment mismatch protection.
- Typed error mapping: `AuthenticationError` (401/403), `ValidationError`
  (400/422), `RateLimitError` (429 + Retry-After), `APIError` (5xx/402/404),
  `NetworkError` (transport), `WebhookVerificationError` (machine-readable reason).
- Bounded exponential retry policy: GET retried on transport/5xx; invoice
  creation retried only with an idempotency key; 429 honors Retry-After (5 s cap).
- Zero-dependency stdlib (urllib) transport with injectable `Transport` protocol.
- pytest suite incl. the documented HMAC test vector (byte-identical fixtures
  with the PHP SDK); ruff-clean; typed public API.
- Examples: create/get invoice, webhook verification, safe handlers for Flask and FastAPI.
