"""Complete, production-safe webhook flow for Flask.

Flow: raw body -> signature verification -> duplicate check -> local order
lookup -> invoice/amount/asset validation -> mark paid -> mark event
processed -> HTTP 200.

Never trust a browser success/return URL as proof of payment.

Run:  pip install flask && ZEROKYC_API_KEY=pk_test_... \
      ZEROKYC_WEBHOOK_SECRET=whsec_... python safe_webhook_handler_flask.py
"""

import os

from flask import Flask, request

from zerokyc import ReplayGuard, ZeroKYC

app = Flask(__name__)

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
def webhook():
    # 1. Signature + timestamp first, before touching the payload.
    try:
        event = zkp.verify_webhook(request.get_data(), request.headers.get("X-ZKP-Signature", ""))
    except Exception:
        return "invalid signature", 400

    # 2. At-least-once delivery: skip duplicates, answer 200 so retries stop.
    if guard.is_duplicate(event.id):
        return "", 200

    # 3. Only confirmation events mark orders paid.
    if not event.is_payment_confirmed:
        return "", 200

    order = load_order(event.invoice_id or "")
    if order is None:
        return "", 200  # unknown invoice: investigate manually, don't brick the queue

    # 4. Signature validity alone is NOT enough: match invoice/amount/asset.
    if not guard.matches_order(
        event,
        order["expected_invoice_id"],
        min_amount=order["expected_amount"],
        asset=order["expected_asset"],
    ):
        app.logger.error("zerokyc: event %s did not match its order", event.id)
        return "", 200

    # 5. Belt and suspenders for high-value orders: confirm server-to-server.
    # invoice = zkp.get_invoice(event.invoice_id)
    # if not invoice.is_paid: return "", 200

    # 6. TODO mark the order paid in YOUR system (activate service, email...)

    # 7. Mark processed only AFTER the order update succeeded.
    guard.mark_processed(event.id)
    return "", 200


if __name__ == "__main__":
    app.run(port=8080)
