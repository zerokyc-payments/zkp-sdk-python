"""HTTP client with typed error mapping and a bounded, idempotency-aware
retry policy. Adapters never talk to the API directly.

Retry rules (identical to the PHP SDK):
- GET: retry NetworkError and selected retryable statuses (429/408/5xx);
- POST invoices: retry ONLY when an idempotency key is present;
- 429: honors Retry-After up to a 5s cap;
- 400/401/403/422: never retried;
- bounded exponential backoff (300ms -> 600ms -> 1200ms), no infinite loops.

Secrets never appear in exceptions: messages carry API-provided text only.
"""

from __future__ import annotations

import json
import re
import time as _time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from .config import Config
from .exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ValidationError,
)
from .http import HttpResponse, urllib_transport
from .idempotency import assert_valid
from .models.invoice import CreateInvoiceResponse, Invoice
from .models.webhook import WebhookEvent
from .webhooks.verifier import WebhookVerifier

# plain decimal only: no sign, no exponent, no NaN/Infinity spellings
_AMOUNT_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")

_RETRYABLE_STATUSES = frozenset({429, 408})
_RETRY_AFTER_CAP_SECONDS = 5


class ZeroKYC:
    """Facade - the single entry point integrations should use.

    >>> zkp = ZeroKYC(api_key="pk_test_...", environment="sandbox")
    >>> response = zkp.create_invoice("19.90", "USD", order_id="INV-1042",
    ...                               idempotency_key="zerokyc:myshop:order:1042")
    >>> redirect(response.invoice.checkout_url)
    """

    def __init__(
        self,
        api_key: str,
        environment: str | None = None,
        webhook_secret: str = "",
        timeout: float = 15.0,
        max_retries: int = 2,
        base_url: str | None = None,
        transport: Callable[..., HttpResponse] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.config = Config(
            api_key=api_key,
            environment=environment,
            webhook_secret=webhook_secret,
            timeout=timeout,
            max_retries=max_retries,
            base_url=base_url or "https://api.zerokyc-payments.com",
        )
        self._transport = transport or urllib_transport
        self._sleeper = sleeper or _time.sleep

    # --- invoices -------------------------------------------------------------

    def create_invoice(
        self,
        amount: str,
        currency: str = "USD",
        *,
        order_id: str | None = None,
        description: str | None = None,
        payment_currency: str = "any",
        ttl_minutes: int | None = None,
        webhook_url: str | None = None,
        success_url: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> CreateInvoiceResponse:
        """Create an invoice; with an idempotency key a timeout+retry returns
        the same invoice instead of creating a duplicate."""
        payload = _build_create_payload(
            amount=amount,
            base_currency=currency,
            payment_currency=payment_currency,
            order_id=order_id,
            description=description,
            ttl_minutes=ttl_minutes,
            webhook_url=webhook_url,
            success_url=success_url,
            metadata=metadata,
        )
        if idempotency_key is not None:
            assert_valid(idempotency_key)

        headers = {"Content-Type": "application/json"}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        response = self._request(
            "POST",
            "/v1/invoices",
            headers=headers,
            body=json.dumps(payload).encode(),
            may_retry=idempotency_key is not None,
            expected_status=201,
        )
        replay = (response.header("Idempotent-Replay") or "").lower() == "true"
        return CreateInvoiceResponse(Invoice.from_dict(_json(response)), replay)

    def get_invoice(self, invoice_id: str) -> Invoice:
        """Reconciliation/recovery: poll a status server-to-server (webhook
        loss, cron checks, support tooling)."""
        response = self._request(
            "GET", f"/v1/invoices/{_quote(invoice_id)}", may_retry=True, expected_status=200
        )
        return Invoice.from_dict(_json(response))

    def cancel_invoice(self, invoice_id: str) -> Invoice:
        response = self._request(
            "POST",
            f"/v1/invoices/{_quote(invoice_id)}/cancel",
            headers={"Content-Type": "application/json"},
            body=b"{}",
            may_retry=False,
            expected_status=200,
        )
        return Invoice.from_dict(_json(response))

    def ping(self) -> dict[str, Any]:
        response = self._request("GET", "/v1/ping", may_retry=True, expected_status=200)
        return _json(response)

    # --- webhooks -------------------------------------------------------------

    def verify_webhook(
        self,
        raw_body: bytes | str,
        signature_header: str,
        *,
        secret: str | None = None,
    ) -> WebhookEvent:
        """Verify a delivery; raises WebhookVerificationError on any failure."""
        return self.verifier(secret).verify(raw_body, signature_header)

    def verifier(self, secret: str | None = None) -> WebhookVerifier:
        return WebhookVerifier(secret if secret is not None else self.config.webhook_secret)

    # --- transport ------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        may_retry: bool = False,
        expected_status: int = 200,
    ) -> HttpResponse:
        attempt = 0
        while True:
            try:
                response = self._transport(
                    method,
                    self.config.base_url + path,
                    headers={
                        **(headers or {}),
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Accept": "application/json",
                    },
                    body=body,
                    timeout=self.config.timeout,
                )
            except NetworkError:
                if not may_retry or attempt >= self.config.max_retries:
                    raise
                self._sleeper(_backoff_ms(attempt) / 1000)
                attempt += 1
                continue

            if response.status == expected_status:
                return response

            if (
                response.status in _RETRYABLE_STATUSES or response.status >= 500
            ) and may_retry and attempt < self.config.max_retries:
                delay_ms: float | None
                if response.status == 429:
                    delay_ms = _retry_after_ms(response.header("Retry-After"))
                else:
                    delay_ms = _backoff_ms(attempt)
                if delay_ms is not None:
                    self._sleeper(delay_ms / 1000)
                    attempt += 1
                    continue
                # Retry-After beyond the cap: fall through and surface the 429

            raise _map_error(response)


def _map_error(response: HttpResponse) -> Exception:
    error = {}
    try:
        decoded = json.loads(response.body)
        if isinstance(decoded, dict) and isinstance(decoded.get("error"), dict):
            error = decoded["error"]
    except ValueError:
        pass
    message = str(error.get("message") or f"unexpected HTTP {response.status}")
    code = error.get("code")
    doc_url = error.get("doc_url")

    if response.status in (401, 403):
        return AuthenticationError(message)
    if response.status == 429:
        return RateLimitError(message, _parse_retry_after(response.header("Retry-After")))
    if response.status in (400, 422):
        return ValidationError(message)
    return APIError(message, status=response.status, error_code=code, doc_url=doc_url)


def _json(response: HttpResponse) -> dict[str, Any]:
    try:
        decoded = json.loads(response.body)
    except ValueError as e:
        raise APIError("response was not valid JSON", status=response.status) from e
    if not isinstance(decoded, dict):
        raise APIError("response was not a JSON object", status=response.status)
    return decoded


def _backoff_ms(attempt: int) -> float:
    return 300.0 * (2**attempt)


def _parse_retry_after(header: str | None) -> int | None:
    """Seconds from a Retry-After header, or None when absent/unsupported.

    Only plain non-negative integers are supported; HTTP-date and any
    malformed value (incl. negative or fractional) safely map to None.
    """
    if header is None:
        return None
    value = header.strip()
    return int(value) if value.isdigit() else None


def _retry_after_ms(header: str | None) -> float | None:
    """Delay for a 429 retry: Retry-After when valid and within the cap,
    default backoff when the header is absent, None (give up waiting) for a
    valid value beyond the cap or an unsupported/malformed format."""
    if header is None:
        return _backoff_ms(0)
    seconds = _parse_retry_after(header)
    if seconds is None:
        # malformed or HTTP-date: unsupported -> report retry_after=None,
        # still retry on the default bounded backoff
        return _backoff_ms(0)
    return seconds * 1000 if seconds <= _RETRY_AFTER_CAP_SECONDS else None


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def _build_create_payload(
    *,
    amount: str,
    base_currency: str,
    payment_currency: str,
    order_id: str | None,
    description: str | None,
    ttl_minutes: int | None,
    webhook_url: str | None,
    success_url: str | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    # local validation mirrors the API rules so obvious mistakes never leave
    # the process (never the only line of defense)
    if not isinstance(amount, str) or not _AMOUNT_RE.match(amount):
        raise ValidationError(f"amount must be a plain positive decimal string, got {amount!r}")
    amount_dec = Decimal(amount)
    if not amount_dec.is_finite() or amount_dec <= 0:
        # the regex already rejects NaN/sNaN/Infinity/-Infinity/0/negatives;
        # is_finite() stays as a belt-and-suspenders guard
        raise ValidationError(f"amount must be a positive finite decimal, got {amount!r}")
    if not base_currency:
        raise ValidationError("currency must not be empty")
    if ttl_minutes is not None and not 10 <= ttl_minutes <= 4320:
        raise ValidationError("ttl_minutes must be between 10 and 4320")
    if order_id is not None and len(order_id) > 255:
        raise ValidationError("order_id must be at most 255 characters")
    if description is not None and len(description) > 500:
        raise ValidationError("description must be at most 500 characters")
    if webhook_url is not None and len(webhook_url) > 2000:
        raise ValidationError("webhook_url must be at most 2000 characters")
    if success_url is not None and len(success_url) > 2000:
        raise ValidationError("success_url must be at most 2000 characters")

    payload: dict[str, Any] = {
        "amount": str(amount),
        "base_currency": base_currency,
        "payment_currency": payment_currency,
    }
    if order_id is not None:
        payload["order_id"] = order_id
    if description is not None:
        payload["description"] = description
    if ttl_minutes is not None:
        payload["ttl_minutes"] = ttl_minutes
    if webhook_url is not None:
        payload["webhook_url"] = webhook_url
    if success_url is not None:
        payload["success_url"] = success_url
    if metadata:
        payload["metadata"] = metadata
    return payload
