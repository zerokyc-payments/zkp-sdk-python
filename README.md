# zkp-sdk-python

Official Python SDK for the [ZeroKYC Pay](https://zerokyc-payments.com) crypto payment gateway.
Framework-agnostic, zero third-party runtime dependencies (standard library only), Python 3.10+,
fully typed.

The same public contract and security guarantees as
[zkp-sdk-php](https://github.com/zerokyc-payments/zkp-sdk-php): API client, webhook
verification, idempotency, status normalization and payment matching are done for you.

## Install

```bash
pip install zkp-sdk-python
```

(If the package is not on PyPI yet, install from source:

```bash
pip install git+https://github.com/zerokyc-payments/zkp-sdk-python.git
```
)

## Quickstart (sandbox invoice in 5 minutes)

1. Create an account at [console.zerokyc-payments.com](https://console.zerokyc-payments.com)
   and copy a **sandbox** API key (`pk_test_...`) from *API keys*.
2. Create an invoice and send the buyer to the hosted checkout:

```python
import os
from zerokyc import ZeroKYC, idempotency_key

zkp = ZeroKYC(api_key=os.environ["ZEROKYC_API_KEY"], environment="sandbox")

response = zkp.create_invoice(
    "19.90", "USD",
    order_id="INV-1042",
    description="VPS plan: starter",
    idempotency_key=idempotency_key("myshop", "order", 1042),  # stable per local order
)
print(response.invoice.checkout_url)   # redirect the buyer here
```

3. Get paid: ZeroKYC detects the on-chain payment and POSTs a signed webhook.
   **A verified webhook (or a server-side `get_invoice()`) is the only proof of
   payment — never a browser success URL.**

```python
from zerokyc.exceptions import WebhookVerificationError

try:
    event = zkp.verify_webhook(request.body, request.headers["X-ZKP-Signature"])
except WebhookVerificationError:
    return Response(status=400)

if event.is_payment_confirmed:
    ...  # match invoice/amount/asset, then activate the order
```

Full production flow with duplicate protection and payment matching:
[examples/safe_webhook_handler_flask.py](examples/safe_webhook_handler_flask.py) /
[examples/safe_webhook_handler_fastapi.py](examples/safe_webhook_handler_fastapi.py).

## API surface

| Method | Purpose |
|---|---|
| `create_invoice(amount, currency, ...)` | create an invoice (idempotent with `idempotency_key`) |
| `get_invoice(invoice_id)` | reconciliation / polling / lost-webhook recovery |
| `cancel_invoice(invoice_id)` | cancel an unpaid invoice |
| `ping()` | liveness / configuration probe |
| `verify_webhook(raw_body, signature_header)` | HMAC verification of a delivery |

## Configuration

`ZeroKYC(api_key=..., environment=..., webhook_secret=..., timeout=15.0, max_retries=2, base_url=...)`

- `api_key`: `pk_test_...` (sandbox) / `pk_live_...` (production).
- `environment`: `"sandbox"` / `"production"`; inferred from the key; a mismatch raises
  `ValueError` instead of hoping for the best.
- `webhook_secret`: `whsec_...` from console → Webhooks (used by `verify_webhook`).
- `base_url`: tests/local development only — the URL is defined centrally.

## Status normalization

Raw API statuses never leak into your billing logic:

| API (raw)                | `InvoiceStatus`              |
|--------------------------|------------------------------|
| `created`, `pending`     | `PENDING`                    |
| `detecting`              | `CONFIRMING`                 |
| `confirmed`              | `PAID`                       |
| `underpaid`              | `UNDERPAID`                  |
| `expired`                | `EXPIRED`                    |
| `canceled`               | `CANCELLED`                  |
| unknown                  | `FAILED` (alert)             |

`invoice.is_paid` / `invoice.is_terminal` answer the common questions.

## Idempotency

```python
from zerokyc import idempotency_key
idempotency_key("whmcs", "invoice", 1042)  # zerokyc:whmcs:invoice:1042 (<=120 chars)
```

A timeout + retry then returns **the same** invoice
(`CreateInvoiceResponse.idempotent_replay is True`) instead of a duplicate.

## Error handling & retries

| Exception                  | HTTP         | Retried automatically? |
|----------------------------|--------------|------------------------|
| `AuthenticationError`      | 401 / 403    | never                  |
| `ValidationError`          | 400 / 422    | never                  |
| `RateLimitError`           | 429          | yes (Retry-After up to 5s, max twice) |
| `APIError`                 | 5xx, 402, 404| only GET / idempotent POST |
| `NetworkError`             | transport    | only GET / idempotent POST |
| `WebhookVerificationError` | n/a          | n/a (machine-readable `.reason`) |

Backoff is bounded exponential (300ms → 600ms → 1200ms, capped by `max_retries`).

## Webhook security checklist

- verify against the **exact raw body** (never re-serialized JSON);
- strict `t=`/`v1=` header format, lowercase hex, constant-time compare (built in);
- default ±300 s window (`WebhookVerifier(secret, 600)` to widen);
- at-least-once delivery: `ReplayGuard.is_duplicate()` is a **pure** check —
  call `mark_processed()` only after the local order update succeeded;
- match invoice id / amount / asset before crediting (`ReplayGuard.matches_order()`);
- secrets never appear in exceptions or logs.

Self-test against the documented vector:

```python
from zerokyc import WebhookVerifier

event = WebhookVerifier("whsec_zkp_test_vector_2026").verify(
    '{"id":"evt_test_001","type":"payment.confirmed","invoice_id":"inv_test_001"}',
    "t=1788788073,v1=ade537fa13aec79a6d1648bd7f197872066c161676c389243ab5c6b13fea7f52",
    now=1788788073,
)
```

## Assets

USDT (TRC-20), USDC/USDT (Polygon, Arbitrum), BTC, XMR, TON, USDT-TON. Pin one via
`payment_currency="USDT_TRON"`, or let the buyer choose with `"any"` (default).

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## License

MIT — see [LICENSE](LICENSE).
