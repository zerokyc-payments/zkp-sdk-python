"""Retry-After handling: 429 always raises RateLimitError; malformed,
negative, fractional or HTTP-date values never explode and report
retry_after=None; sleeps are never negative and honor the 5s cap."""

from __future__ import annotations

import json
from typing import Any

import pytest

from zerokyc import RateLimitError, ZeroKYC
from zerokyc.http import HttpResponse

HTTP_DATE = "Wed, 21 Oct 2026 07:28:00 GMT"


def make_rate_limited_sdk(retry_after: str | None):
    def transport(*args: Any, **kwargs: Any) -> HttpResponse:
        headers = {"Retry-After": retry_after} if retry_after is not None else {}
        return HttpResponse(429, json.dumps({"error": {"code": "rate_limited",
                                                       "message": "slow down"}}), headers)

    slept: list[float] = []
    sdk = ZeroKYC(api_key="pk_test_demo", environment="sandbox",
                  base_url="https://api.test", transport=transport, sleeper=slept.append)
    return sdk, slept


def _rate_limit(sdk) -> RateLimitError:
    with pytest.raises(RateLimitError) as excinfo:
        sdk.get_invoice("inv_1")
    return excinfo.value


def test_retry_after_3_seconds():
    sdk, slept = make_rate_limited_sdk("3")
    err = _rate_limit(sdk)
    assert err.retry_after == 3
    assert slept == [3.0, 3.0]  # max_retries=2, sleeping exactly the header value


def test_retry_after_0_seconds():
    sdk, slept = make_rate_limited_sdk("0")
    err = _rate_limit(sdk)
    assert err.retry_after == 0
    assert slept == [0.0, 0.0]


def test_retry_after_above_cap_gives_up_immediately():
    sdk, slept = make_rate_limited_sdk("9")
    err = _rate_limit(sdk)
    assert err.retry_after == 9
    assert slept == []  # beyond the 5s cap: no waiting, surface the 429


def test_retry_after_not_a_number():
    sdk, slept = make_rate_limited_sdk("not-a-number")
    err = _rate_limit(sdk)
    assert err.retry_after is None
    assert slept == [0.3, 0.3]  # default bounded backoff, never negative


def test_retry_after_http_date_unsupported():
    sdk, slept = make_rate_limited_sdk(HTTP_DATE)
    err = _rate_limit(sdk)
    assert err.retry_after is None
    assert slept == [0.3, 0.3]


def test_retry_after_negative_rejected():
    sdk, slept = make_rate_limited_sdk("-1")
    err = _rate_limit(sdk)
    assert err.retry_after is None
    assert all(s >= 0 for s in slept)


def test_retry_after_fractional_rejected():
    sdk, slept = make_rate_limited_sdk("1.5")
    err = _rate_limit(sdk)
    assert err.retry_after is None
    assert all(s >= 0 for s in slept)


def test_retry_after_missing():
    sdk, slept = make_rate_limited_sdk(None)
    err = _rate_limit(sdk)
    assert err.retry_after is None
    assert slept == [0.3, 0.3]


def test_rate_limit_error_is_never_value_error():
    """Regression: int('not-a-number') used to leak ValueError from _map_error."""
    for header in ("not-a-number", HTTP_DATE, "-1", "1.5", ""):
        sdk, _ = make_rate_limited_sdk(header)
        err = _rate_limit(sdk)
        assert isinstance(err, RateLimitError)
