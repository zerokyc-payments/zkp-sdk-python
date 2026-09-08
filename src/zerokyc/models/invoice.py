"""Typed invoice models (create + get responses share the shape)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..status import InvoiceStatus, StatusMapper

__all__ = ["Invoice", "InvoiceStatus", "CreateInvoiceResponse"]


@dataclass(frozen=True)
class Invoice:
    id: str
    order_id: str | None = None
    description: str | None = None
    amount: str = ""
    base_currency: str = ""
    payment_currency: str = ""
    raw_status: str = ""
    status: InvoiceStatus = InvoiceStatus.FAILED
    ttl_minutes: int = 0
    expires_at: str = ""
    created_at: str = ""
    checkout_url: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    options: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    paid_amount: str | None = None
    paid_asset: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Invoice:
        raw_status = str(data.get("status", ""))
        return cls(
            id=str(data.get("id", "")),
            order_id=data.get("order_id"),
            description=data.get("description"),
            amount=str(data.get("amount", "")),
            base_currency=str(data.get("base_currency", "")),
            payment_currency=str(data.get("payment_currency", "")),
            raw_status=raw_status,
            status=StatusMapper.normalize(raw_status) or InvoiceStatus.FAILED,
            ttl_minutes=int(data.get("ttl_minutes") or 0),
            expires_at=str(data.get("expires_at", "")),
            created_at=str(data.get("created_at", "")),
            checkout_url=str(data.get("checkout_url", "")),
            metadata=dict(data.get("metadata") or {}),
            options=list(data.get("options") or []),
            observations=list(data.get("observations") or []),
            paid_amount=(
                str(data["paid_amount"]) if data.get("paid_amount") is not None else None
            ),
            paid_asset=(
                str(data["paid_asset"]) if data.get("paid_asset") is not None else None
            ),
            raw=dict(data),
        )

    @property
    def is_paid(self) -> bool:
        return self.status is InvoiceStatus.PAID

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    def option(self, asset: str) -> dict[str, Any] | None:
        """Payment option by asset id (e.g. ``USDT_TRON``), or ``None``."""
        for option in self.options:
            if option.get("asset") == asset:
                return option
        return None


@dataclass(frozen=True)
class CreateInvoiceResponse:
    invoice: Invoice
    # True when the API returned a previously created invoice for the same
    # Idempotency-Key (safe timeout/retry path).
    idempotent_replay: bool = False
