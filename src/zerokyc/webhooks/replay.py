"""At-least-once delivery protection and payment matching.

``is_duplicate()`` is a PURE check: it never mutates the store. An event is
marked processed only via :meth:`ReplayGuard.mark_processed` AFTER the local
order update succeeded - marking earlier would turn any crash in between into
a permanently unpaid order (the retry would be skipped as a duplicate).

Concurrent deliveries of the same event can both pass ``is_duplicate()``;
apps needing strict single-processing should implement an atomic claim
(``INSERT ... ON CONFLICT`` / unique constraint) in their EventStore and use
it as the source of truth.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Protocol

from ..models.webhook import WebhookEvent


class EventStore(Protocol):
    """Storage-agnostic processed-event guard (your DB/cache implements this)."""

    def has(self, event_id: str) -> bool: ...

    def mark_processed(self, event_id: str) -> None: ...


def _to_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


class ReplayGuard:
    def __init__(self, store: EventStore) -> None:
        self._store = store

    def is_duplicate(self, event_id: str) -> bool:
        """Pure check: True when the event was already processed. No side effects."""
        return self._store.has(event_id)

    def mark_processed(self, event_id: str) -> None:
        """Call only after the local order update has succeeded."""
        self._store.mark_processed(event_id)

    def matches_order(
        self,
        event: WebhookEvent,
        expected_invoice_id: str,
        min_amount: str | None = None,
        asset: str | None = None,
    ) -> bool:
        """Signature validity alone is NOT enough to credit an order: match
        the invoice id, the paid crypto amount (>= ``min_amount``) and the
        asset. ``asset`` accepts a bare ticker ("USDT") or an asset id
        ("USDT_TRON" - the network part must then match too).
        """
        if event.invoice_id != expected_invoice_id:
            return False
        if asset is not None and not self._asset_matches(event, asset):
            return False
        if min_amount is not None:
            paid = event.paid_amount
            if paid is None:
                return False
            paid_dec = _to_decimal(paid)
            min_dec = _to_decimal(min_amount)
            if paid_dec is None or min_dec is None or paid_dec < min_dec:
                return False
        return True

    @staticmethod
    def _asset_matches(event: WebhookEvent, expected: str) -> bool:
        paid_raw = (event.paid_asset or "").lower()
        if not paid_raw:
            return False
        exp_ticker, _, exp_network = expected.lower().partition("_")
        paid_ticker, _, paid_rest = paid_raw.partition("_")
        if paid_ticker != exp_ticker:
            return False
        paid_network = (event.paid_network or "").lower() or paid_rest
        if exp_network and paid_network and paid_network != exp_network:
            return False
        return True
