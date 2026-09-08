"""Webhook verification tests - same cases and vector as the PHP SDK."""

from __future__ import annotations

import pytest

from zerokyc import WebhookVerificationError
from zerokyc.webhooks.verifier import WebhookVerifier

VECTOR_SECRET = "whsec_zkp_test_vector_2026"
VECTOR_BODY = '{"id":"evt_test_001","type":"payment.confirmed","invoice_id":"inv_test_001"}'
VECTOR_TS = 1788788073
VECTOR_SIG = "ade537fa13aec79a6d1648bd7f197872066c161676c389243ab5c6b13fea7f52"
VECTOR_HEADER = f"t={VECTOR_TS},v1={VECTOR_SIG}"


def make_verifier(secret: str = VECTOR_SECRET, tolerance: int = 300) -> WebhookVerifier:
    return WebhookVerifier(secret, tolerance)


def test_accepts_documented_test_vector():
    event = make_verifier().verify(VECTOR_BODY, VECTOR_HEADER, now=VECTOR_TS)
    assert event.id == "evt_test_001"
    assert event.type == "payment.confirmed"
    assert event.invoice_id == "inv_test_001"
    assert event.is_payment_confirmed


def test_accepts_bytes_body():
    event = make_verifier().verify(VECTOR_BODY.encode(), VECTOR_HEADER, now=VECTOR_TS)
    assert event.id == "evt_test_001"


def test_rejects_wrong_secret():
    with pytest.raises(WebhookVerificationError, match="signature does not match"):
        WebhookVerifier("whsec_some_other_secret").verify(VECTOR_BODY, VECTOR_HEADER, now=VECTOR_TS)


def test_rejects_modified_body():
    forged = VECTOR_BODY.replace("inv_test_001", "inv_evil_999")
    result = make_verifier().check(forged, VECTOR_HEADER, now=VECTOR_TS)
    assert not result.valid
    assert result.reason == WebhookVerificationError.SIGNATURE_MISMATCH


def test_rejects_stale_timestamp():
    result = make_verifier().check(VECTOR_BODY, VECTOR_HEADER, now=VECTOR_TS + 301)
    assert result.reason == WebhookVerificationError.STALE_TIMESTAMP


def test_rejects_future_timestamp():
    result = make_verifier().check(VECTOR_BODY, VECTOR_HEADER, now=VECTOR_TS - 301)
    assert result.reason == WebhookVerificationError.FUTURE_TIMESTAMP


def test_accepts_edge_of_tolerance_window():
    result = make_verifier().check(VECTOR_BODY, VECTOR_HEADER, now=VECTOR_TS + 300)
    assert result.valid


@pytest.mark.parametrize(
    "header,reason",
    [
        ("", WebhookVerificationError.MISSING_HEADER),
        ("garbage", WebhookVerificationError.MALFORMED_HEADER),
        (f"t=abc,v1={VECTOR_SIG}", WebhookVerificationError.MALFORMED_HEADER),
        (f"t={VECTOR_TS}", WebhookVerificationError.MALFORMED_HEADER),
        (f"v1={VECTOR_SIG}", WebhookVerificationError.MALFORMED_HEADER),
        (f"t={VECTOR_TS},v1={VECTOR_SIG.upper()}", WebhookVerificationError.MALFORMED_HEADER),
        (f"t={VECTOR_TS},v1={VECTOR_SIG},extra=1", WebhookVerificationError.MALFORMED_HEADER),
        ("t=1788788073,v1=deadbeef", WebhookVerificationError.MALFORMED_HEADER),
    ],
)
def test_rejects_malformed_headers(header: str, reason: str):
    result = make_verifier().check(VECTOR_BODY, header, now=VECTOR_TS)
    assert not result.valid
    assert result.reason == reason


def test_rejects_verified_but_non_json_body():
    verifier = make_verifier()
    header = verifier.sign("not json at all", timestamp=VECTOR_TS)
    result = verifier.check("not json at all", header, now=VECTOR_TS)
    assert result.reason == WebhookVerificationError.MALFORMED_PAYLOAD


def test_rejects_verified_non_object_json():
    verifier = make_verifier()
    body = "[1,2,3]"
    header = verifier.sign(body, timestamp=VECTOR_TS)
    result = verifier.check(body, header, now=VECTOR_TS)
    assert result.reason == WebhookVerificationError.MALFORMED_PAYLOAD


def test_sign_produces_verifiable_header():
    assert make_verifier().sign(VECTOR_BODY, timestamp=VECTOR_TS) == VECTOR_HEADER


def test_empty_secret_rejected():
    with pytest.raises(ValueError):
        WebhookVerifier("")
