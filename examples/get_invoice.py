"""Reconciliation / recovery: poll an invoice status server-to-server.

Usage: python get_invoice.py <invoice-id>   (ZEROKYC_API_KEY env required)
"""

import os
import sys

from zerokyc import InvoiceStatus, ZeroKYC

if len(sys.argv) != 2:
    sys.exit("usage: python get_invoice.py <invoice-id>")

zkp = ZeroKYC(api_key=os.environ["ZEROKYC_API_KEY"], environment="sandbox")
invoice = zkp.get_invoice(sys.argv[1])

print(f"invoice: {invoice.id}")
print(f"status:  {invoice.status.value} (raw: {invoice.raw_status})")
print(f"paid:    {invoice.paid_amount or '-'} {invoice.paid_asset or ''}".rstrip())
print(f"expires: {invoice.expires_at}")

# platform mapping example
actions = {
    InvoiceStatus.PAID: "mark local order paid",
    InvoiceStatus.UNDERPAID: "flag order: contact customer",
    InvoiceStatus.EXPIRED: "close/void local order",
    InvoiceStatus.CANCELLED: "close/void local order",
}
print(f"-> {actions.get(invoice.status, 'keep waiting' if not invoice.is_terminal else 'alert')}")
