"""Client behaviour: DTO parsing, replay flag, error mapping, retry policy,
configuration guards. Uses a stub transport (mirrors the PHP suite)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from zerokyc import (
    APIError,
    AuthenticationError,
    InvoiceStatus,
    NetworkError,
    RateLimitError,
    ValidationError,
    ZeroKYC,
)
from zerokyc.http import HttpResponse

BASE = "https://api.test"


def invoice_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "inv_123",
        "order_id": "INV-1042",
        "description": None,
        "amount": "19.90",
        "base_currency": "USD",
        "payment_currency": "any",
        "status": "created",
        "ttl_minutes": 360,
        "expires_at": "2026-09-08T12:00:00Z",
        "created_at": "2026-09-08T06:00:00Z",
        "checkout_url": "https://pay.test/pay/inv_123",
        "metadata": {},
        "options": [
            {"asset": "USDT_TRON", "network": "tron", "payment_address": "Tabc",
             "amount_crypto": "19.9", "rate": "1", "status": "open"},
            {"asset": "BTC", "network": "bitcoin", "payment_address": "bc1q",
             "amount_crypto": "0.0002", "rate": "99000", "status": "open"},
        ],
        "observations": [],
        "paid_amount": None,
        "paid_asset": None,
    }
    payload.update(overrides)
    return payload


def make_sdk(response: HttpResponse, *, sleeper: list | None = None) -> ZeroKYC:
    def transport(*args: Any, **kwargs: Any) -> HttpResponse:
        return response

    def sleep_noop(seconds: float) -> None:
        if sleeper is not None:
            sleeper.append(seconds)

    return ZeroKYC(
        api_key="pk_test_demo",
        environment="sandbox",
        base_url=BASE,
        transport=transport,
        sleeper=sleep_noop,
    )


def test_create_invoice_parses_dto():
    sdk = make_sdk(HttpResponse(201, json.dumps(invoice_payload()), {"idempotent-replay": "false"}))
    result = sdk.create_invoice("19.90", "USD", order_id="INV-1042",
                                idempotency_key="zerokyc:test:invoice:1042")

    assert result.invoice.id == "inv_123"
    assert result.invoice.status is InvoiceStatus.PENDING
    assert result.invoice.raw_status == "created"
    assert result.invoice.checkout_url == "https://pay.test/pay/inv_123"
    assert result.idempotent_replay is False
    assert len(result.invoice.options) == 2
    assert result.invoice.option("USDT_TRON") is not None
    assert result.invoice.option("SOL") is None


def test_idempotent_replay_flag_from_header_case_insensitive():
    sdk = make_sdk(HttpResponse(201, json.dumps(invoice_payload()), {"Idempotent-Replay": "TRUE"}))
    result = sdk.create_invoice("5.00")
    assert result.idempotent_replay is True


def test_get_invoice_paid():
    sdk = make_sdk(
        HttpResponse(
            200,
            json.dumps(
                invoice_payload(status="confirmed", paid_amount="19.9", paid_asset="USDT_TRON")
            ),
            {},
        )
    )
    invoice = sdk.get_invoice("inv_123")
    assert invoice.is_paid
    assert invoice.status is InvoiceStatus.PAID
    assert invoice.paid_amount == "19.9"


@pytest.mark.parametrize(
    "status,exc",
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (400, ValidationError),
        (422, ValidationError),
        (429, RateLimitError),
        (500, APIError),
        (402, APIError),
        (404, APIError),
    ],
)
def test_error_mapping(status: int, exc: type[Exception]):
    sdk = make_sdk(
        HttpResponse(
            status,
            json.dumps({"error": {"code": "x", "message": "boom", "doc_url": None}}),
            {"Retry-After": "12"} if status == 429 else {},
        )
    )
    with pytest.raises(exc, match="boom"):
        sdk.get_invoice("inv_123")


def test_rate_limit_carries_retry_after():
    sdk = make_sdk(
        HttpResponse(
            429,
            json.dumps({"error": {"code": "rate_limited", "message": "slow down"}}),
            {"Retry-After": "9"},
        )
    )
    with pytest.raises(RateLimitError) as excinfo:
        sdk.get_invoice("inv_123")
    assert excinfo.value.retry_after == 9


def test_local_request_validation():
    sdk = make_sdk(HttpResponse(201, "{}", {}))
    with pytest.raises(ValidationError):
        sdk.create_invoice("abc")
    with pytest.raises(ValidationError):
        sdk.create_invoice("5.00", ttl_minutes=5)


def test_config_rejects_sandbox_key_in_production():
    with pytest.raises(ValueError, match="sandbox key"):
        ZeroKYC(api_key="pk_test_demo", environment="production")


def test_config_rejects_live_key_in_sandbox():
    with pytest.raises(ValueError, match="not a sandbox key"):
        ZeroKYC(api_key="pk_live_demo", environment="sandbox")


def test_environment_inferred_from_key():
    assert ZeroKYC(api_key="pk_test_demo").config.is_sandbox
    assert not ZeroKYC(api_key="pk_live_demo").config.is_sandbox


class FlakyTransport:
    """Fails N times with NetworkError, then returns a canned response."""

    def __init__(self, fail_times: int, response: HttpResponse) -> None:
        self.fail_times = fail_times
        self.response = response
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> HttpResponse:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise NetworkError("timeout")
        return self.response


def test_get_retries_network_errors_with_backoff():
    transport = FlakyTransport(99, HttpResponse(200, json.dumps(invoice_payload()), {}))
    slept: list[float] = []
    sdk = ZeroKYC(api_key="pk_test_demo", environment="sandbox", base_url=BASE,
                  transport=transport, sleeper=slept.append)

    with pytest.raises(NetworkError):
        sdk.get_invoice("inv_1")
    assert transport.calls == 3  # 1 + 2 retries
    assert slept == [0.3, 0.6]  # bounded exponential backoff, seconds


def test_post_without_idempotency_key_is_not_retried():
    transport = FlakyTransport(99, HttpResponse(201, json.dumps(invoice_payload()), {}))
    sdk = ZeroKYC(api_key="pk_test_demo", environment="sandbox", base_url=BASE,
                  transport=transport, sleeper=lambda s: None)

    with pytest.raises(NetworkError):
        sdk.create_invoice("5.00")
    assert transport.calls == 1


def test_post_with_idempotency_key_retries():
    transport = FlakyTransport(1, HttpResponse(201, json.dumps(invoice_payload()), {}))
    sdk = ZeroKYC(api_key="pk_test_demo", environment="sandbox", base_url=BASE,
                  transport=transport, sleeper=lambda s: None)

    result = sdk.create_invoice("5.00", idempotency_key="zerokyc:test:invoice:1")
    assert result.invoice.id == "inv_123"
    assert transport.calls == 2


def test_5xx_retried_on_get_then_surfaces():
    responses = [HttpResponse(503, "oops", {}), HttpResponse(503, "oops", {}),
                 HttpResponse(200, json.dumps(invoice_payload()), {})]
    calls = {"n": 0}

    def transport(*a: Any, **kw: Any) -> HttpResponse:
        r = responses[calls["n"]]
        calls["n"] += 1
        return r

    sdk = ZeroKYC(api_key="pk_test_demo", environment="sandbox", base_url=BASE,
                  transport=transport, sleeper=lambda s: None)
    invoice = sdk.get_invoice("inv_1")
    assert invoice.id == "inv_123"
    assert calls["n"] == 3


def test_secrets_never_in_exceptions():
    sdk = make_sdk(
        HttpResponse(
            401, json.dumps({"error": {"code": "unauthorized", "message": "invalid key"}}), {}
        )
    )
    try:
        sdk.get_invoice("inv_1")
        raise AssertionError("expected")
    except AuthenticationError as e:
        assert "pk_test_demo" not in str(e)
        assert "Bearer" not in str(e)
