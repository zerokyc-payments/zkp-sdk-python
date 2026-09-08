"""Status mapping, idempotency keys, replay guard purity and payment matching."""

from __future__ import annotations

import pytest

from zerokyc import InvoiceStatus, StatusMapper, WebhookEvent, idempotency_key
from zerokyc.webhooks.replay import ReplayGuard


class InMemoryEventStore:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def has(self, event_id: str) -> bool:
        return event_id in self._seen

    def mark_processed(self, event_id: str) -> None:
        self._seen.add(event_id)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("created", InvoiceStatus.PENDING),
        ("pending", InvoiceStatus.PENDING),
        ("detecting", InvoiceStatus.CONFIRMING),
        ("confirmed", InvoiceStatus.PAID),
        ("underpaid", InvoiceStatus.UNDERPAID),
        ("expired", InvoiceStatus.EXPIRED),
        ("canceled", InvoiceStatus.CANCELLED),
    ],
)
def test_status_mapping(raw: str, expected: InvoiceStatus):
    assert StatusMapper.normalize(raw) is expected


def test_unknown_status_normalizes_to_none():
    assert StatusMapper.normalize("something-new") is None
    with pytest.raises(ValueError):
        StatusMapper.normalize_or_fail("nope")


def test_terminal_states():
    for raw in ("confirmed", "underpaid", "expired", "canceled"):
        assert StatusMapper.is_terminal(raw)
    for raw in ("created", "pending", "detecting"):
        assert not StatusMapper.is_terminal(raw)


def test_idempotency_key_format():
    assert idempotency_key("whmcs", "invoice", 1042) == "zerokyc:whmcs:invoice:1042"
    with pytest.raises(ValueError):
        idempotency_key("platform", "x" * 100, "y" * 30)


def test_is_duplicate_is_pure_until_mark_processed():
    """A crash between the check and the order update must NOT lose the retry."""
    guard = ReplayGuard(InMemoryEventStore())

    assert guard.is_duplicate("evt_1") is False
    assert guard.is_duplicate("evt_1") is False  # still unprocessed

    guard.mark_processed("evt_1")
    assert guard.is_duplicate("evt_1") is True
    assert guard.is_duplicate("evt_2") is False


def _prod_event() -> WebhookEvent:
    # exact production payload shape (captured live 2026-09-08)
    return WebhookEvent.from_dict(
        {
            "id": "evt_1",
            "type": "payment.confirmed",
            "created_at": "2026-09-08T18:40:00Z",
            "data": {
                "invoice_id": "inv_9",
                "order_id": "O-1",
                "amount": "19.90",
                "base_currency": "USD",
                "option": {
                    "asset": "USDT",
                    "network": "tron",
                    "amount_crypto": "19.9",
                    "paid_amount": "20.5",
                },
            },
        }
    )


def test_matches_order_production_shape():
    guard = ReplayGuard(InMemoryEventStore())
    event = _prod_event()

    assert guard.matches_order(event, "inv_9")
    assert guard.matches_order(event, "inv_9", min_amount="19.90", asset="USDT")  # ticker
    assert guard.matches_order(event, "inv_9", min_amount="19.90", asset="USDT_TRON")  # asset id
    assert guard.matches_order(event, "inv_9", min_amount="20.5", asset="USDT_TRON")
    assert not guard.matches_order(event, "inv_OTHER")  # wrong invoice
    assert not guard.matches_order(event, "inv_9", min_amount="20.6")  # under expected
    assert not guard.matches_order(event, "inv_9", min_amount="19.90", asset="BTC")  # wrong asset
    assert not guard.matches_order(event, "inv_9", min_amount="19.90", asset="USDT_BTC")


def test_matches_order_legacy_docs_shape():
    guard = ReplayGuard(InMemoryEventStore())
    legacy = WebhookEvent.from_dict(
        {
            "id": "evt_2",
            "type": "payment.confirmed",
            "invoice_id": "inv_9",
            "data": {"asset": "USDT_TRON", "amount": "20.5"},
        }
    )
    assert guard.matches_order(legacy, "inv_9", min_amount="19.90", asset="USDT_TRON")


def test_matches_order_missing_amount_data():
    guard = ReplayGuard(InMemoryEventStore())
    event = WebhookEvent.from_dict(
        {"id": "e", "type": "invoice.created", "data": {"invoice_id": "i"}}
    )
    assert not guard.matches_order(event, "i", min_amount="1.00")
