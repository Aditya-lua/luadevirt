"""Core fetch logic for jnkie-hosted obfuscated sources.

STATUS: starter skeleton. The raw HTTP GET works today; the jnkie-specific
steps (URL-form normalization, loader/redirect unwrapping, any key/nonce
handshake) are marked TODO and must be reversed against the live service
before this fetches a real protected payload. Keep the module stdlib-only
(urllib) so the tool stays Node-free and dependency-light, matching
luarmor-fetch.
"""

from __future__ import annotations

import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field

DEFAULT_TIMEOUT = 30
DEFAULT_UA = "jnkie-fetch/0.0.1 (+https://github.com/Aditya-lua/luadevirt)"

# jnkie share/raw URLs seen in the wild tend to look like one of these.
# Confirm and extend against the real service before relying on them.
_JNKIE_HOST_RE = re.compile(r"(?:^|\.)jnkie\.[a-z]+$", re.IGNORECASE)
_JNKIE_ID_RE = re.compile(r"/(?:raw|r|s|v|share)/([A-Za-z0-9_-]+)", re.IGNORECASE)


@dataclass
class FetchResult:
    url: str
    status: int
    body: bytes
    headers: dict = field(default_factory=dict)
    note: str = ""

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class JnkieError(RuntimeError):
    """Raised when a fetch cannot be completed or the response is not usable."""


def normalize_url(url: str) -> str:
    """Turn a user-supplied jnkie URL/ID into a canonical fetch URL.

    TODO(agent): once the real endpoints are known, map a bare share ID or a
    web/share URL to the raw-content endpoint. For now this is a pass-through
    that only validates the input looks like a URL or an ID.
    """
    url = url.strip()
    if not url:
        raise JnkieError("empty URL")
    if url.startswith(("http://", "https://")):
        return url
    # Bare id -> TODO: build the canonical raw URL for the live service.
    if re.fullmatch(r"[A-Za-z0-9_-]+", url):
        raise JnkieError(
            f"bare id {url!r} given but the raw-endpoint template is not yet "
            "known — pass a full https:// jnkie URL, or implement normalize_url"
        )
    raise JnkieError(f"unrecognized jnkie reference: {url!r}")


def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (user-provided URL by design)
            body = resp.read()
            return FetchResult(
                url=resp.geturl(),
                status=getattr(resp, "status", 200),
                body=body,
                headers=dict(resp.headers.items()),
            )
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        raise JnkieError(f"HTTP {exc.code} fetching {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network path
        raise JnkieError(f"network error fetching {url}: {exc.reason}") from exc


def unwrap(result: FetchResult) -> FetchResult:
    """Strip any loader/redirect/wrapper to reach the obfuscated source.

    TODO(agent): jnkie may serve the payload behind a small Lua loader stub, a
    JSON envelope, or a redirect to a signed CDN URL. Detect those here and
    follow/decode them so callers always get the actual obfuscated Lua body.
    Right now this is a no-op that just annotates obvious cases.
    """
    head = result.text[:256].lstrip()
    if head.startswith("{"):
        result.note = "looks like a JSON envelope — unwrap() not yet implemented"
    elif "loadstring" in result.text[:4096] or "HttpGet" in result.text[:4096]:
        result.note = "looks like a loader stub — unwrap() not yet implemented"
    return result


def fetch(url: str, *, timeout: int = DEFAULT_TIMEOUT, raw: bool = False) -> FetchResult:
    """Fetch the obfuscated source for a jnkie URL or share ID.

    :param raw: if True, skip :func:`unwrap` and return the response verbatim.
    """
    canonical = normalize_url(url)
    result = _http_get(canonical, timeout=timeout)
    if not raw:
        result = unwrap(result)
    return result
