"""Complete, production-safe webhook flow for FastAPI.

Flow: raw body -> signature verification -> duplicate check -> local order
lookup -> invoice/amount/asset validation -> mark paid -> mark event
processed -> HTTP 200.

Run:  pip install fastapi uvicorn && ZEROKYC_API_KEY=pk_test_... \
      ZEROKYC_WEBHOOK_SECRET=whsec_... uvicorn safe_webhook_handler_fastapi:app
"""

import os

from fastapi import FastAPI, Request, Response

from zerokyc import ReplayGuard, ZeroKYC

app = FastAPI()

zkp = ZeroKYC(
    api_key=os.environ["ZEROKYC_API_KEY"],
    environment="production",
    webhook_secret=os.environ["ZEROKYC_WEBHOOK_SECRET"],
)


# TODO implement with YOUR database (a one-column processed_events table with
# a unique constraint doubles as the atomic claim)
class InMemoryEventStore:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def has(self, event_id: str) -> bool:
        return event_id in self._seen

    def mark_processed(self, event_id: str) -> None:
        self._seen.add(event_id)


guard = ReplayGuard(InMemoryEventStore())


def load_order(invoice_id: str) -> dict | None:
    """TODO look up the local order by the ZeroKYC invoice id in YOUR tables."""
    return {
        "expected_invoice_id": invoice_id,
        "expected_amount": "19.90",
        "expected_asset": "USDT",
        "paid": False,
    }


@app.post("/webhooks/zerokyc")
async def webhook(request: Request) -> Response:
    # 1. Signature + timestamp first, before touching the payload.
    try:
        event = zkp.verify_webhook(await request.body(), request.headers.get("X-ZKP-Signature", ""))
    except Exception:
        return Response(status_code=400)

    # 2. At-least-once delivery: skip duplicates, answer 200 so retries stop.
    if guard.is_duplicate(event.id):
        return Response(status_code=200)

    # 3. Only confirmation events mark orders paid.
    if not event.is_payment_confirmed:
        return Response(status_code=200)

    order = load_order(event.invoice_id or "")
    if order is None:
        return Response(status_code=200)  # unknown invoice: investigate manually

    # 4. Signature validity alone is NOT enough: match invoice/amount/asset.
    if not guard.matches_order(
        event,
        order["expected_invoice_id"],
        min_amount=order["expected_amount"],
        asset=order["expected_asset"],
    ):
        return Response(status_code=200)

    # 5. Belt and suspenders for high-value orders:
    # invoice = zkp.get_invoice(event.invoice_id)
    # if not invoice.is_paid: return Response(status_code=200)

    # 6. TODO mark the order paid in YOUR system (activate service, email...)

    # 7. Mark processed only AFTER the order update succeeded.
    guard.mark_processed(event.id)
    return Response(status_code=200)
