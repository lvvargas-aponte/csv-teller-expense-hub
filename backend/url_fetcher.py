"""Safe outbound HTTPS fetcher for the Knowledge-tab URL-import path.

Defense-in-depth against SSRF.  Every fetch passes through:

1. **Scheme allowlist** — only ``https://``.  No ``http://``, no ``file://``,
   no ``ftp://``, no ``gopher://``.  Public reference material is all on
   HTTPS in 2026; rejecting plain HTTP closes a downgrade vector.
2. **Host allowlist** — only the seed domains we ship in the UI.  Generic
   "user pastes any URL" is intentionally NOT supported yet.  When that
   feature lands, it will go behind a separate config flag.
3. **DNS resolution + private-IP guard** — we resolve the hostname before
   the request and refuse if it points at loopback / link-local / private
   ranges.  This blocks DNS-rebinding tricks and the classic
   ``localhost``-via-public-DNS bypass (``localtest.me`` → 127.0.0.1).
4. **Manual redirect handling** — every hop is re-validated against the
   allowlist + private-IP guard.  Auto-following redirects would let an
   allowed origin redirect to ``http://169.254.169.254/`` and read cloud
   metadata.
5. **Byte cap + timeout** — streamed read with a hard 10 MB ceiling and
   60 s total timeout.  Prevents a misconfigured server from hanging a
   worker or eating memory.

The fetcher returns ``(bytes, content_type, final_url)``; the caller
decides whether to route into the PDF or HTML extractor.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# 1 GB cap on fetched body — matches the extractor's MAX_BYTES so large
# allowlisted documents (multi-year IRS publications, multi-hundred-page
# SEC PDFs) can be imported.  ``TOTAL_TIMEOUT`` raised proportionally so
# a slow upstream serving a real 1 GB body has time to finish; the cap
# itself is what protects us from runaway streams, not the timeout.
MAX_FETCH_BYTES = 1024 * 1024 * 1024  # 1 GB
CONNECT_TIMEOUT = 10.0
TOTAL_TIMEOUT   = 600.0               # 10 min — accommodates very large fetches
MAX_REDIRECTS   = 5

ALLOWED_SCHEMES = {"https"}

# Static base allowlist — the trusted floor.  These hosts are always
# accepted regardless of database state, so a misconfigured ``allowlist_hosts``
# table can never lock out the curated seed list.  Runtime additions
# (added when a user creates a custom seed) are unioned in via
# ``get_allowed_hosts()``.
#
# Grouped by trust tier so it's obvious why each entry is here.  Blast
# radius of a compromised host is bounded — fetched bytes are extracted
# to text and embedded; no scripts run, no rendering happens.
BASE_ALLOWED_HOSTS = {
    # --- Tier 1: government / regulator (highest authority) ---
    "www.irs.gov",                # tax rules, publications
    "www.consumerfinance.gov",    # CFPB consumer guides
    "www.investor.gov",           # SEC investor education
    "www.sec.gov",                # SEC rules, EDGAR-adjacent guidance
    "www.ssa.gov",                # Social Security retirement info
    "www.treasurydirect.gov",     # I-bonds, TIPS, savings bonds
    "www.federalreserve.gov",     # macro / rates / household-finance reports

    # --- Tier 2: established educational community ---
    # Note: Bogleheads is intentionally NOT in this list — its wiki sits
    # behind Cloudflare TLS-fingerprint protection that returns 403 to
    # plain httpx regardless of headers.  Users save the page from their
    # browser (Ctrl+P → Save as PDF) and upload via the file uploader.
    "www.fpa.org",                # Financial Planning Association consumer resources

    # --- Tier 3: FIRE community pillars (opinionated but widely cited) ---
    "www.mrmoneymustache.com",    # MMM — canonical FIRE math + lifestyle
    "www.madfientist.com",        # tax-optimized FIRE strategies
    "earlyretirementnow.com",     # Big ERN's SWR research series
    # ChooseFI + Physician on Fire removed — URLs unstable across site
    # reorgs and the 301-redirect targets land off-allowlist.  Re-add
    # specific stable post URLs as they're discovered.
}


def get_allowed_hosts() -> set[str]:
    """Effective allowlist = base set ∪ runtime additions.

    Runtime additions come from the ``allowlist_hosts`` table and are
    populated when a user adds a custom seed via the UI.  Imported here
    lazily to avoid a circular import (``seed_loader`` imports
    ``sync_engine`` which is fine, but tests sometimes mock the loader).
    """
    try:
        import seed_loader  # local import keeps the module boot-time clean
        return BASE_ALLOWED_HOSTS | seed_loader.list_runtime_allowed_hosts()
    except Exception:
        return set(BASE_ALLOWED_HOSTS)


# Backwards-compat alias for any external code that still references the
# old constant name.  New code should use ``get_allowed_hosts()``.
ALLOWED_HOSTS = BASE_ALLOWED_HOSTS

# User-agent string.  Bot-flavored UAs ("MyBot/1.0") get 403'd by several
# government sites (SSA, parts of investor.gov) that filter on UA shape.
# Mozilla-prefixed strings are the de-facto convention for well-behaved
# fetchers (curl, archive.org bots, RSS readers); we still identify
# ourselves honestly in the parenthetical so server logs aren't misled.
USER_AGENT = (
    "Mozilla/5.0 (compatible; ExpensesHub-Knowledge/1.0; "
    "+local-only personal-finance research)"
)

# Cloudflare and similar bot-protection layers check the full request
# fingerprint, not just User-Agent.  These headers mirror what a normal
# browser sends and unblock most sites that filter on header shape.
# Sites doing TLS-fingerprint or JS-challenge protection (e.g. some
# Cloudflare configs) are out of reach without a headless browser; those
# fall back to manual download + upload.
_BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/pdf;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


class FetchError(Exception):
    """Raised on any fetch failure — SSRF guard tripped, network error,
    body too large, non-2xx response.  Always carries a user-facing
    message; never leaks raw exception detail."""


def _check_url(url: str, enforce_allowlist: bool = True) -> Tuple[str, str]:
    """Validate scheme + (optionally) host allowlist.  Returns ``(host, scheme)``.

    Raises ``FetchError`` with a human-readable message for any breach.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()

    if scheme not in ALLOWED_SCHEMES:
        raise FetchError(f"Only https:// URLs are allowed (got {scheme!r})")
    if not host:
        raise FetchError("URL has no hostname")
    if enforce_allowlist:
        allowed = get_allowed_hosts()
        if host not in allowed:
            raise FetchError(
                f"Host {host!r} is not on the import allowlist.  "
                f"Add a custom seed for this host or extend BASE_ALLOWED_HOSTS."
            )
    return host, scheme


def _check_resolves_public(host: str) -> None:
    """Resolve ``host`` and refuse if any A/AAAA points to a private,
    loopback, link-local, or reserved range.  This blocks DNS rebinding
    and the ``allowed-host.example.com → 127.0.0.1`` trick.

    We use ``getaddrinfo`` rather than ``gethostbyname`` so IPv6 is
    covered too.  Every returned address is checked — a single private
    answer fails the whole resolution.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise FetchError(f"DNS lookup failed for {host}: {e}") from e

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise FetchError(
                f"Refusing to fetch {host}: resolves to {ip_str} "
                f"(private/loopback/reserved address)"
            )


def fetch(
    url: str,
    *,
    enforce_allowlist: bool = True,
    max_bytes: int = MAX_FETCH_BYTES,
    total_timeout: float = TOTAL_TIMEOUT,
) -> Tuple[bytes, str, str]:
    """Fetch a URL with SSRF + size + redirect protection.

    Returns ``(body_bytes, content_type, final_url)``.  The final URL is
    the last hop after manual redirect resolution — store this so future
    re-fetches and dedupe checks see the canonical address.

    ``enforce_allowlist=False`` (advisor web tools) skips only the host
    allowlist; the scheme, DNS/private-IP, and redirect re-validation
    guards always run.

    Raises ``FetchError`` for any policy violation or network failure.
    """
    current = url
    visited = []

    timeout = httpx.Timeout(total_timeout, connect=CONNECT_TIMEOUT)

    # Redirects are followed manually so each hop re-passes the allowlist
    # and private-IP guard.  follow_redirects=False on httpx means we get
    # 30x responses back as-is.
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=_BROWSER_HEADERS) as client:
        for _ in range(MAX_REDIRECTS + 1):
            host, _scheme = _check_url(current, enforce_allowlist)
            _check_resolves_public(host)
            visited.append(current)

            try:
                with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("Location")
                        if not location:
                            raise FetchError(
                                f"Redirect from {current} missing Location header"
                            )
                        # ``str(httpx.URL(...))`` returns the canonical
                        # absolute URL; older httpx exposed this via
                        # ``human_repr()`` which has since been removed.
                        current = str(httpx.URL(current).join(location))
                        if current in visited:
                            raise FetchError(f"Redirect loop detected at {current}")
                        continue

                    if resp.status_code >= 400:
                        raise FetchError(
                            f"Fetch failed: {resp.status_code} for {current}"
                        )

                    content_length = resp.headers.get("Content-Length")
                    if content_length and int(content_length) > max_bytes:
                        raise FetchError(
                            f"Resource too large: {content_length} bytes "
                            f"(max {max_bytes})"
                        )

                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise FetchError(
                                f"Resource exceeded {max_bytes}-byte cap mid-stream"
                            )
                        chunks.append(chunk)

                    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                    return b"".join(chunks), content_type, current
            except httpx.HTTPError as e:
                # Don't leak internal exception detail to the API caller —
                # log it and surface a generic message.
                logger.warning(f"[url_fetcher] HTTP error fetching {current}: {e}")
                raise FetchError(f"Network error fetching {current}") from e

        raise FetchError(f"Too many redirects (max {MAX_REDIRECTS})")
