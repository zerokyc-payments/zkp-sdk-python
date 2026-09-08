"""HTTP transport: stdlib-only default (urllib) plus an injectable protocol.

The default transport intentionally has no third-party dependencies; tests
and platform adapters can inject any callable matching :class:`Transport`.
"""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from .exceptions import NetworkError

Headers = dict[str, str]


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str
    headers: Headers

    def __init__(self, status: int, body: str, headers: Headers | None = None) -> None:
        # normalize once: header() lookups are case-insensitive by contract
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "body", body)
        object.__setattr__(
            self, "headers", {str(k).lower(): v for k, v in (headers or {}).items()}
        )

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


class Transport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        headers: Headers | None = None,
        body: bytes | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        """Perform one HTTP request; raise NetworkError on transport failures."""
        ...


def urllib_transport(
    method: str,
    url: str,
    headers: Headers | None = None,
    body: bytes | None = None,
    timeout: float | None = None,
) -> HttpResponse:
    """Zero-dependency transport built on :mod:`urllib.request`.

    Sends an SDK User-Agent: the default ``Python-urllib/x.y`` signature is
    blocked by many CDNs (Cloudflare browser-integrity returns 403/1010), and
    an identifiable agent is proper SDK etiquette anyway. An explicit
    User-Agent in ``headers`` wins.
    """
    from . import __version__

    merged = {f"User-Agent": f"zerokyc-python/{__version__}"}
    merged.update(headers or {})
    req = urllib.request.Request(
        url=url,
        data=body,
        method=method.upper(),
        headers=merged,
    )
    # never follow redirects: a 3xx must surface, not silently convert a POST
    opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        with opener.open(req, timeout=timeout or 15.0) as resp:
            raw = resp.read()
            return HttpResponse(
                status=resp.status,
                body=raw.decode("utf-8", "replace"),
                headers={k.lower(): v for k, v in resp.headers.items()},
            )
    except urllib.error.HTTPError as e:  # non-2xx arrives here
        raw = e.read()
        return HttpResponse(
            status=e.code,
            body=raw.decode("utf-8", "replace"),
            headers={k.lower(): v for k, v in (e.headers or {}).items()},
        )
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as e:
        reason = getattr(e, "reason", None) or e
        raise NetworkError(f"transport failure: {reason}") from e


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        return None


__all__ = ["HttpResponse", "Transport", "urllib_transport", "Headers"]
