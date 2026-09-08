"""Webhook signature verification - security critical.

Every delivery carries one header::

    X-ZKP-Signature: t=<unix seconds>,v1=<64-char lowercase hex>

``v1`` is HMAC-SHA256(webhook_secret, "{t}.{raw_body}") where raw_body is the
exact request body as received - never re-serialized JSON. Verification is
strict (header format, ±tolerance window) and constant-time.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time

from ..exceptions import WebhookVerificationError as WVE
from ..models.webhook import VerificationResult, WebhookEvent

_HEADER_RE = re.compile(r"^t=(\d{1,12}),v1=([0-9a-f]{64})$")

DEFAULT_TOLERANCE = 300

_MESSAGES = {
    WVE.MISSING_HEADER: "X-ZKP-Signature header is missing",
    WVE.MALFORMED_HEADER: "signature header is malformed (expected t=<int>,v1=<64 lowercase hex>)",
    WVE.STALE_TIMESTAMP: "signature timestamp is outside the tolerance window (stale)",
    WVE.FUTURE_TIMESTAMP: "signature timestamp is outside the tolerance window (future)",
    WVE.SIGNATURE_MISMATCH: "signature does not match the raw body",
    WVE.MALFORMED_PAYLOAD: "verified body is not a JSON object",
}


class WebhookVerifier:
    def __init__(self, webhook_secret: str, tolerance_seconds: int = DEFAULT_TOLERANCE) -> None:
        if not webhook_secret:
            raise ValueError("webhook secret must not be empty")
        if tolerance_seconds < 1:
            raise ValueError("tolerance must be at least 1 second")
        self._secret = webhook_secret.encode()
        self.tolerance = tolerance_seconds

    def verify(
        self,
        raw_body: bytes | str,
        signature_header: str,
        *,
        now: int | None = None,
    ) -> WebhookEvent:
        """Verify and decode; raises WebhookVerificationError on any failure."""
        result = self.check(raw_body, signature_header, now=now)
        if result.event is None:
            raise WVE(
                _MESSAGES.get(result.reason or "", "verification failed"),
                result.reason or "invalid",
            )
        return result.event

    def check(
        self,
        raw_body: bytes | str,
        signature_header: str,
        *,
        now: int | None = None,
    ) -> VerificationResult:
        """Non-raising variant returning a :class:`VerificationResult`."""
        if not signature_header:
            return VerificationResult(False, WVE.MISSING_HEADER, None)
        m = _HEADER_RE.match(signature_header)
        if m is None:
            return VerificationResult(False, WVE.MALFORMED_HEADER, None)
        timestamp, signature = m.group(1), m.group(2)

        current = time.time() if now is None else now
        skew = current - int(timestamp)
        if skew > self.tolerance:
            return VerificationResult(False, WVE.STALE_TIMESTAMP, None)
        if -skew > self.tolerance:
            return VerificationResult(False, WVE.FUTURE_TIMESTAMP, None)

        expected = self._sign(str(timestamp), raw_body)
        if not hmac.compare_digest(expected, signature):
            return VerificationResult(False, WVE.SIGNATURE_MISMATCH, None)

        try:
            if isinstance(raw_body, bytes):
                raw_body = raw_body.decode("utf-8")
            payload = json.loads(raw_body)
        except (ValueError, UnicodeDecodeError):
            return VerificationResult(False, WVE.MALFORMED_PAYLOAD, None)
        if not isinstance(payload, dict):
            return VerificationResult(False, WVE.MALFORMED_PAYLOAD, None)

        return VerificationResult(True, None, WebhookEvent.from_dict(payload))

    def sign(self, raw_body: bytes | str, timestamp: int | None = None) -> str:
        """Build a signature header for a body (tests and local replay tooling)."""
        ts = int(time.time()) if timestamp is None else timestamp
        return f"t={ts},v1={self._sign(str(ts), raw_body)}"

    def _sign(self, timestamp: str, raw_body: bytes | str) -> str:
        body = raw_body if isinstance(raw_body, bytes) else raw_body.encode()
        return hmac.new(self._secret, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
