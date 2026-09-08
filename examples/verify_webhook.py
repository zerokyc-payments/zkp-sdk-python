"""Minimal webhook signature verification.

Framework integration: pass the exact raw body and the X-ZKP-Signature
header from the request - never re-serialized JSON.
"""

import os

from zerokyc import WebhookVerifier
from zerokyc.exceptions import WebhookVerificationError

verifier = WebhookVerifier(os.environ["ZEROKYC_WEBHOOK_SECRET"], tolerance_seconds=300)

try:
    # WSGI:      raw = environ["wsgi.input"].read(int(environ["CONTENT_LENGTH"]))
    # Django:    raw = request.body
    # FastAPI:   raw = await request.body()
    raw_body = b"..."  # exact raw bytes as received
    header = ""  # request.headers["X-ZKP-Signature"]
    event = verifier.verify(raw_body, header)
except WebhookVerificationError as e:
    # respond 400; log the machine-readable reason
    raise SystemExit(f"rejected: {e.reason}") from e

print(f"verified event {event.type} for invoice {event.invoice_id}")
