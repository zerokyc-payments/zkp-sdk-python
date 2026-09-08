"""Normalized invoice status enum + raw-API status mapping.

Raw statuses (``created/pending/detecting/confirmed/underpaid/expired/canceled``)
never leak into billing logic: platforms consume :class:`InvoiceStatus`
(mirrors the PHP SDK enum).
"""

from __future__ import annotations

from enum import Enum


class InvoiceStatus(str, Enum):
    PENDING = "PENDING"          # created / pending
    CONFIRMING = "CONFIRMING"    # seen on-chain, awaiting confirmations
    PAID = "PAID"                # confirmed and credited
    EXPIRED = "EXPIRED"
    UNDERPAID = "UNDERPAID"
    OVERPAID = "OVERPAID"        # reserved: currently credited as PAID server-side
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"            # unknown/unexpected state - alert

    @property
    def is_terminal(self) -> bool:
        return self not in (InvoiceStatus.PENDING, InvoiceStatus.CONFIRMING)


_MAP: dict[str, InvoiceStatus] = {
    "created": InvoiceStatus.PENDING,
    "pending": InvoiceStatus.PENDING,
    "detecting": InvoiceStatus.CONFIRMING,
    "confirmed": InvoiceStatus.PAID,
    "underpaid": InvoiceStatus.UNDERPAID,
    "expired": InvoiceStatus.EXPIRED,
    "canceled": InvoiceStatus.CANCELLED,
    # overpayment is credited and confirmed server-side; kept for forward
    # compatibility and local bookkeeping
    "overpaid": InvoiceStatus.OVERPAID,
}

_RAW_TERMINAL = frozenset({"confirmed", "underpaid", "expired", "canceled"})


class StatusMapper:
    @staticmethod
    def normalize(raw: str) -> InvoiceStatus | None:
        return _MAP.get(raw)

    @staticmethod
    def normalize_or_fail(raw: str) -> InvoiceStatus:
        status = _MAP.get(raw)
        if status is None:
            raise ValueError(f"unknown invoice status {raw!r}")
        return status

    @staticmethod
    def is_terminal(raw: str) -> bool:
        return raw in _RAW_TERMINAL

    @staticmethod
    def is_paid(raw: str) -> bool:
        return raw == "confirmed"
