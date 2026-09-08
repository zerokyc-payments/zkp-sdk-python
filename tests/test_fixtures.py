"""Fixtures are byte-identical to the PHP SDK's - cross-language contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zerokyc.webhooks.verifier import WebhookVerifier

FIXTURES = Path(__file__).parent / "fixtures" / "webhooks"
SECRET = "whsec_fixture_secret"


@pytest.mark.parametrize(
    "filename,expected_type,expected_invoice",
    [
        ("confirmed.json", "payment.confirmed", "inv_fixture_001"),
        ("underpaid.json", "payment.underpaid", "inv_fixture_002"),
        ("expired.json", "invoice.expired", "inv_fixture_003"),
        ("pending.json", "payment.detected", "inv_fixture_004"),
    ],
)
def test_fixture_verifies_and_parses(filename: str, expected_type: str, expected_invoice: str):
    body = (FIXTURES / filename).read_text(encoding="utf-8")
    verifier = WebhookVerifier(SECRET)
    event = verifier.verify(body, verifier.sign(body))

    assert event.type == expected_type
    assert event.invoice_id == expected_invoice
    assert event.id


def test_confirmed_fixture_carries_payment_data():
    body = (FIXTURES / "confirmed.json").read_text(encoding="utf-8")
    verifier = WebhookVerifier(SECRET)
    event = verifier.verify(body, verifier.sign(body))

    assert event.is_payment_confirmed
    assert event.paid_asset == "USDT"
    assert event.paid_network == "tron"
    assert event.paid_amount == "19.9"
    payload = json.loads(body)
    assert payload["data"]["order_id"] == "INV-1042"
