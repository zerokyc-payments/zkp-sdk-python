"""Create a sandbox invoice and print the hosted-checkout URL.

Set your key first (console -> API keys):  export ZEROKYC_API_KEY=pk_test_...
"""

import os

from zerokyc import ZeroKYC, idempotency_key

zkp = ZeroKYC(api_key=os.environ["ZEROKYC_API_KEY"], environment="sandbox")

response = zkp.create_invoice(
    "19.90", "USD",
    order_id="INV-1042",
    description="VPS plan: starter",
    payment_currency="any",
    # stable key: a crash + retry returns the same invoice, never a duplicate
    idempotency_key=idempotency_key("example", "demo", "20260908"),
)

invoice = response.invoice
print(f"invoice:  {invoice.id}")
print(f"status:   {invoice.status.value} (raw: {invoice.raw_status})")
print(f"amount:   {invoice.amount} {invoice.base_currency}")
print(f"replay:   {'yes (same invoice returned)' if response.idempotent_replay else 'no'}")
print(f"checkout: {invoice.checkout_url}")
for option in invoice.options:
    print(f"  - {option['asset']} on {option['network']}: "
          f"{option['amount_crypto']} -> {option['payment_address']}")
