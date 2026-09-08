"""Stable idempotency keys so a timeout + retry can never create two
invoices for one local order. Recommended format::

    zerokyc:{platform}:{entity}:{id}   # zerokyc:myshop:order:1042
"""

from __future__ import annotations

MAX_LENGTH = 120


def idempotency_key(platform: str, entity: str, id_: str | int) -> str:
    key = f"zerokyc:{platform}:{entity}:{id_}"
    assert_valid(key)
    return key


def assert_valid(key: str) -> None:
    if not key:
        raise ValueError("idempotency key must not be empty")
    if len(key) > MAX_LENGTH:
        raise ValueError(f"idempotency key must be at most {MAX_LENGTH} characters")
