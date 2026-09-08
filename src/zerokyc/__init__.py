"""Official Python SDK for the ZeroKYC Pay crypto payment gateway.

Quickstart::

    from zerokyc import ZeroKYC

    zkp = ZeroKYC(api_key="pk_test_...", environment="sandbox")
    response = zkp.create_invoice("19.90", "USD", order_id="INV-1042",
                                  idempotency_key="zerokyc:myshop:order:1042")
    print(response.invoice.checkout_url)

Webhooks::

    event = zkp.verify_webhook(request.body, request.headers["X-ZKP-Signature"])
"""

from .client import ZeroKYC
from .config import Config
from .exceptions import (
    APIError,
    AuthenticationError,
    NetworkError,
    RateLimitError,
    ValidationError,
    WebhookVerificationError,
    ZeroKYCError,
)
from .idempotency import assert_valid as assert_idempotency_key
from .idempotency import idempotency_key
from .models.invoice import CreateInvoiceResponse, Invoice, InvoiceStatus
from .models.webhook import VerificationResult, WebhookEvent
from .status import StatusMapper
from .webhooks.replay import EventStore, ReplayGuard
from .webhooks.verifier import WebhookVerifier

__version__ = "0.1.0"

__all__ = [
    "ZeroKYC",
    "Config",
    "Invoice",
    "InvoiceStatus",
    "CreateInvoiceResponse",
    "WebhookEvent",
    "VerificationResult",
    "WebhookVerifier",
    "ReplayGuard",
    "EventStore",
    "StatusMapper",
    "idempotency_key",
    "assert_idempotency_key",
    "ZeroKYCError",
    "APIError",
    "AuthenticationError",
    "ValidationError",
    "RateLimitError",
    "NetworkError",
    "WebhookVerificationError",
]
