"""Amount validation: only finite positive plain decimals pass, and every
failure surfaces as the public ValidationError (never decimal internals)."""

from __future__ import annotations

import decimal

import pytest

from zerokyc import ValidationError, ZeroKYC
from zerokyc.http import HttpResponse


def make_sdk() -> ZeroKYC:
    def transport(*args, **kwargs):  # noqa: ANN002, ANN003
        return HttpResponse(201, "{}", {})

    return ZeroKYC(
        api_key="pk_test_demo",
        environment="sandbox",
        base_url="https://api.test",
        transport=transport,
        sleeper=lambda s: None,
    )


@pytest.mark.parametrize(
    "amount",
    ["19.90", "1", "0.01", "1000000.000001", "0.1", "999999999999"],
)
def test_valid_amounts_pass_validation(amount: str):
    result = make_sdk().create_invoice(amount, "USD")
    assert result is not None


@pytest.mark.parametrize(
    "amount",
    [
        "NaN",
        "sNaN",
        "-NaN",
        "Infinity",
        "-Infinity",
        "+Infinity",
        "inf",
        "0",
        "0.0",
        "00.00",
        "-1",
        "-0.5",
        "",
        "   ",
        "abc",
        "19,90",
        "1e3",
        "1E-2",
        "1.5e2",
        "0x10",
        "12.",
        ".99",
        "+1",
        "1 000",
        "1_000",
        "ноль",
    ],
)
def test_invalid_amounts_raise_validation_error(amount: str):
    with pytest.raises(ValidationError) as excinfo:
        make_sdk().create_invoice(amount, "USD")
    # public message, no decimal internals leaked
    assert "amount" in str(excinfo.value)


def test_non_string_amounts_raise_validation_error():
    for bad in (19.90, 100, None, b"19.90", decimal.Decimal("19.90"), float("nan")):
        with pytest.raises(ValidationError):
            make_sdk().create_invoice(bad, "USD")  # type: ignore[arg-type]


def test_amount_kept_as_string_without_float_roundtrip():
    captured: dict[str, HttpResponse] = {}

    def transport(method, url, headers=None, body=None, timeout=None):  # noqa: ANN001
        captured["body"] = body
        return HttpResponse(201, "{}", {})

    sdk = ZeroKYC(api_key="pk_test_demo", environment="sandbox", base_url="https://api.test",
                  transport=transport, sleeper=lambda s: None)
    sdk.create_invoice("0.1", "USD")
    assert b'"amount": "0.1"' in captured["body"]
