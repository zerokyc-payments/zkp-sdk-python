"""Verified webhook event model.

Production payloads keep the invoice id inside ``data`` and the paid asset as
a TICKER nested in ``data.option``; the docs test vector uses a simplified
top-level shape. Both resolve transparently (same as the PHP SDK).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WebhookEvent:
    id: str
    type: str
    invoice_id: str | None
    data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WebhookEvent:
        data = dict(payload.get("data") or {})
        invoice_id = payload.get("invoice_id")
        if invoice_id is None:
            invoice_id = data.get("invoice_id")
        return cls(
            id=str(payload.get("id", "")),
            type=str(payload.get("type", "")),
            invoice_id=str(invoice_id) if invoice_id is not None else None,
            data=data,
            raw=dict(payload),
        )

    @property
    def is_payment_confirmed(self) -> bool:
        return self.type == "payment.confirmed"

    @property
    def paid_amount(self) -> str | None:
        """Crypto amount actually received (``data.option.paid_amount``,
        docs-vector shape: ``data.amount``). For non-stable assets compare
        against the ``amount_crypto`` you invoiced, not the base total."""
        option = self.data.get("option") or {}
        paid = option.get("paid_amount") if isinstance(option, dict) else None
        if paid is None:
            paid = self.data.get("amount_paid", self.data.get("amount"))
        return str(paid) if paid not in (None, "") else None

    @property
    def paid_asset(self) -> str | None:
        """Ticker the payment arrived in ("USDT") or asset id ("USDT_TRON")."""
        option = self.data.get("option") or {}
        asset = option.get("asset") if isinstance(option, dict) else None
        if asset is None:
            asset = self.data.get("asset")
        return str(asset) if asset not in (None, "") else None

    @property
    def paid_network(self) -> str | None:
        option = self.data.get("option") or {}
        network = option.get("network") if isinstance(option, dict) else None
        return str(network) if network not in (None, "") else None


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    reason: str | None = None
    event: WebhookEvent | None = None
