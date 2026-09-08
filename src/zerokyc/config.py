"""SDK configuration: sandbox/production, base URL, timeouts, retries.

The base URL is defined centrally here. The override exists for tests and
local development only - adapters must never hard-code URLs.
"""

from __future__ import annotations

DEFAULT_BASE_URL = "https://api.zerokyc-payments.com"

SANDBOX = "sandbox"
PRODUCTION = "production"


class Config:
    __slots__ = (
        "api_key", "environment", "webhook_secret", "timeout", "max_retries", "base_url",
    )

    def __init__(
        self,
        api_key: str,
        environment: str | None = None,
        webhook_secret: str = "",
        timeout: float = 15.0,
        max_retries: int = 2,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if environment is None:
            environment = SANDBOX if api_key.startswith("pk_test_") else PRODUCTION
        if environment not in (SANDBOX, PRODUCTION):
            raise ValueError(f"environment must be 'sandbox' or 'production', got {environment!r}")
        # Mixing up sandbox and live keys is the classic production incident:
        # refuse the mismatch outright instead of hoping for the best.
        is_test_key = api_key.startswith("pk_test_")
        if environment == PRODUCTION and is_test_key:
            raise ValueError(
                "environment is production but the api_key is a sandbox key (pk_test_...); "
                "use a pk_live_... key or set environment='sandbox'"
            )
        if environment == SANDBOX and not is_test_key:
            raise ValueError(
                "environment is sandbox but the api_key is not a sandbox key; "
                "expected a pk_test_... key"
            )
        if not 0 <= max_retries <= 5:
            raise ValueError("max_retries must be between 0 and 5")

        self.api_key = api_key
        self.environment = environment
        self.webhook_secret = webhook_secret
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = base_url.rstrip("/")

    @property
    def is_sandbox(self) -> bool:
        return self.environment == SANDBOX
