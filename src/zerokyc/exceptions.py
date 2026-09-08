"""Typed exception hierarchy.

Mapping: 401/403 -> AuthenticationError, 400/422 -> ValidationError,
429 -> RateLimitError (carries Retry-After), 5xx/402/404 -> APIError,
transport failures -> NetworkError, webhook verification ->
WebhookVerificationError (machine-readable ``reason``).

Secrets never appear in messages: they carry API-provided text and status
codes only.
"""

from __future__ import annotations


class ZeroKYCError(Exception):
    """Base class for every error this SDK raises."""


class AuthenticationError(ZeroKYCError):
    """401/403 from the API: missing/invalid key or forbidden scope. Never retried."""


class ValidationError(ZeroKYCError):
    """400/422 from the API (or local request validation). Never retried."""


class RateLimitError(ZeroKYCError):
    """429 from the API; ``retry_after`` carries the Retry-After seconds when sent."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class APIError(ZeroKYCError):
    """Unexpected API error (5xx, 402 cutoff, 404, malformed envelope)."""

    def __init__(
        self,
        message: str,
        status: int = 0,
        error_code: str | None = None,
        doc_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.doc_url = doc_url


class NetworkError(ZeroKYCError):
    """Transport failure: DNS, connect, TLS or timeout."""


class WebhookVerificationError(ZeroKYCError):
    """Webhook verification failed; ``reason`` is machine-readable."""

    MISSING_HEADER = "missing_header"
    MALFORMED_HEADER = "malformed_header"
    STALE_TIMESTAMP = "stale_timestamp"
    FUTURE_TIMESTAMP = "future_timestamp"
    SIGNATURE_MISMATCH = "signature_mismatch"
    MALFORMED_PAYLOAD = "malformed_payload"

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason
