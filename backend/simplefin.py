"""
SimpleFinClient — all SimpleFIN Bridge HTTP interaction lives here.

SimpleFIN (https://www.simplefin.org) is a flat-fee bank/credit-card
aggregator built for personal-finance apps rather than multi-tenant fintech
products. Route handlers call methods on the module-level ``simplefin``
instance (created in ``state.py``) and never touch httpx directly.

Auth model: the user visits their SimpleFIN Bridge in a browser, connects
banks there, and generates a one-time "Setup Token" (base64 of a claim URL).
The backend claims it exactly once to get back an "Access URL" — a URL with
HTTP Basic Auth credentials embedded in its userinfo component. That access
URL is the durable credential and is reused for every future
accounts/transactions fetch.

Important: SimpleFIN has no per-account disconnect endpoint. One access URL
covers every account the user connected in a given Bridge session, so
"disconnecting" a single account (routers/simplefin.py) is a local hide, not
a revoke at SimpleFIN.

Mocking in tests: patch individual async methods on the instance, e.g.
    patch.object(state.simplefin, "list_accounts_by_url", AsyncMock(return_value=([], [])))
"""
import base64
import hashlib
import logging
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import HTTPException

from config import DEBUG

logger = logging.getLogger(__name__)

# Keyword heuristics used to guess an account's type/subtype — SimpleFIN's
# protocol carries no account-type field at all, so this is a best-effort
# default. Users can correct a misclassified account's balance sign via the
# existing manual balance-override endpoint if a heuristic ever guesses wrong.
_CREDIT_KEYWORDS = ("credit card", "credit", "visa", "mastercard", "amex", "discover", "card")
_LOAN_KEYWORDS = ("loan", "mortgage")
_SAVINGS_KEYWORDS = ("saving", "hysa", "money market")


def mask_url(url: str) -> str:
    """Return a safely loggable representation of an access URL (strip credentials).

    Display only — every access URL from the same Bridge shares a host and
    path, so masked forms are NOT unique. Use ``connection_id`` to identify
    a connection.
    """
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://***@{parts.hostname or '?'}{parts.path}"
    except Exception:
        return "***"


def connection_id(access_url: str) -> str:
    """Stable, URL-safe, non-secret identifier for an access URL.

    The credentials live in the URL's userinfo, so the URL itself can't be
    handed to the frontend; and masking collapses every connection from the
    same Bridge onto the same string (``https://***@bridge.simplefin.org/
    simplefin``), which would make deletes ambiguous. A truncated digest is
    unique per connection and leaks nothing.
    """
    return hashlib.sha256(access_url.encode("utf-8")).hexdigest()[:16]


def _detail(public_msg: str, debug_msg: str) -> str:
    """Return verbose debug detail in dev; a safe public message in production."""
    return debug_msg if DEBUG else public_msg


def _split_auth(access_url: str) -> Tuple[str, Optional[Tuple[str, str]]]:
    """Split an access URL into (base_url_without_credentials, (user, pass) | None)."""
    parts = urlsplit(access_url)
    auth = (parts.username, parts.password or "") if parts.username is not None else None
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    base = urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))
    return base, auth


def infer_account_bucket(
    name: str, org_name: str, raw_balance: Optional[float] = None
) -> Tuple[str, str]:
    """Best-effort ``(type, subtype)`` guess from account/institution name text.

    "credit union" is stripped before matching — an enormous share of US
    credit unions have "Credit Union" literally in their name, which would
    otherwise false-positive every single one of their accounts (checking,
    savings, escrow, ...) as a credit card.

    When no keyword matches at all (e.g. a card product name like "Blue Cash
    Everyday" that doesn't contain "card" or "credit"), ``raw_balance`` — if
    given — breaks the tie: a negative balance on an unlabeled account is a
    far stronger signal of a credit-type (liability) account than of a
    genuinely overdrawn depository one.
    """
    text = f"{name} {org_name}".lower().replace("credit union", "")
    if any(kw in text for kw in _LOAN_KEYWORDS):
        return "credit", "loan"
    if any(kw in text for kw in _CREDIT_KEYWORDS):
        return "credit", "credit_card"
    if any(kw in text for kw in _SAVINGS_KEYWORDS):
        return "depository", "savings"
    if raw_balance is not None and raw_balance < 0:
        return "credit", "credit_card"
    return "depository", "checking"


def iter_normalized_accounts(
    url_batches: List[Tuple[str, List[Dict[str, Any]]]],
    is_hidden: Callable[[str], bool],
) -> Iterator[Dict[str, Any]]:
    """Yield one normalized dict per visible account across every batch.

    The single place that turns a raw SimpleFIN account into the fields the
    app cares about — id, institution, name, balance, and the inferred
    type/subtype. ``/accounts`` and the balances cache both build their own
    output shape from this so they can never drift on what an account *is*
    or on which accounts are visible.

    ``is_hidden`` is injected (rather than reading ``state`` here) to keep
    this module free of app-state imports. Duplicate ids across access URLs
    are yielded once.
    """
    seen: set = set()
    for _url, accounts in url_batches:
        for acct in accounts:
            acct_id = acct.get("id")
            if not acct_id or acct_id in seen or is_hidden(acct_id):
                continue
            seen.add(acct_id)

            org_name = acct.get("_org_name") or "Bank"
            name = acct.get("name") or acct_id
            try:
                raw_balance = float(acct.get("balance") or 0.0)
            except (TypeError, ValueError):
                raw_balance = 0.0

            acct_type, acct_subtype = infer_account_bucket(name, org_name, raw_balance)
            yield {
                "id": acct_id,
                "institution": org_name,
                "name": name,
                "type": acct_type,
                "subtype": acct_subtype,
                "raw_balance": raw_balance,
            }


class SimpleFinClient:
    """Encapsulates all SimpleFIN Bridge API calls.

    Constructor args:
        access_urls — list of access URLs (shared reference from state.py,
                      so appends/removes in state stay visible here)
    """

    def __init__(self, access_urls: List[str]) -> None:
        self._urls = access_urls

    def remove_by_id(self, conn_id: str) -> Optional[str]:
        """Remove and return the access URL whose ``connection_id`` matches.

        Lets a connection be deleted from a value the frontend can safely
        hold — the raw URL embeds Basic Auth credentials and never leaves
        the backend after claiming.
        """
        match = next((u for u in self._urls if connection_id(u) == conn_id), None)
        if match:
            self._urls.remove(match)
        return match

    # ── Claim ────────────────────────────────────────────────────────────

    @staticmethod
    async def claim_setup_token(setup_token: str) -> str:
        """Exchange a one-time Setup Token for a durable Access URL.

        The token is base64 of a claim URL; POSTing to that claim URL (once —
        it is single-use) returns the Access URL as the response body.
        """
        token = "".join((setup_token or "").split())  # strip all whitespace/newlines
        if not token:
            raise HTTPException(status_code=422, detail="setup_token must not be empty.")

        padded = token + "=" * (-len(token) % 4)
        claim_url: Optional[str] = None
        for decoder in (base64.urlsafe_b64decode, base64.b64decode):
            try:
                claim_url = decoder(padded.encode()).decode("utf-8").strip()
                break
            except Exception:
                continue
        if not claim_url or not claim_url.startswith("http"):
            raise HTTPException(status_code=422, detail="Could not decode setup token into a claim URL.")

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            try:
                resp = await client.post(claim_url, content=b"")
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=_detail(
                        "SimpleFIN could not claim this setup token — it may already be used or expired.",
                        f"Claim failed ({e.response.status_code}): {e.response.text}",
                    ),
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=_detail("Connection error while claiming setup token.", f"Connection error: {e}"),
                )

        access_url = resp.text.strip()
        if not access_url.startswith("http"):
            raise HTTPException(status_code=502, detail="SimpleFIN returned an unexpected claim response.")
        return access_url

    # ── Accounts + transactions ─────────────────────────────────────────

    async def list_accounts_by_url(
        self,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
    ) -> Tuple[List[Tuple[str, List[Dict[str, Any]]]], List[Dict[str, Any]]]:
        """GET /accounts?version=2 for every stored access URL.

        Transactions come bundled inline on each account, so no second
        per-account call is needed. ``start_date``/``end_date``
        are Unix timestamps (seconds) per the SimpleFIN protocol.

        Returns ``(successes, errors)`` where successes is
        ``[(access_url, accounts_list), ...]`` and errors is
        ``[{"id": connection_id, "label": masked, "error": str}, ...]``.
        """
        successes: List[Tuple[str, List[Dict[str, Any]]]] = []
        errors: List[Dict[str, Any]] = []

        params: Dict[str, Any] = {"version": 2}
        if start_date is not None:
            params["start-date"] = start_date
        if end_date is not None:
            params["end-date"] = end_date

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            for url in self._urls:
                base_url, auth = _split_auth(url)
                masked = mask_url(url)
                try:
                    resp = await client.get(f"{base_url}/accounts", params=params, auth=auth)
                    resp.raise_for_status()
                    payload = resp.json()
                    accounts = payload.get("accounts", []) or []
                    top_errors = payload.get("errors") or payload.get("errlist") or []
                    for err in top_errors:
                        logger.warning(f"[SimpleFIN] {masked} reported: {err}")

                    # version=2 nests institution name under a top-level
                    # "connections" array, joined by each account's conn_id —
                    # NOT inline per account. (Some implementations may still
                    # inline an "org" object per account, so that's tried
                    # first.) Resolved once here so every caller downstream
                    # gets the real bank name via acct["_org_name"] instead of
                    # duplicating this lookup.
                    conn_names = {
                        c.get("conn_id"): c.get("org_name")
                        for c in (payload.get("connections") or [])
                        if c.get("conn_id")
                    }
                    for acct in accounts:
                        inline_org = (acct.get("org") or {}).get("name")
                        acct["_org_name"] = (
                            inline_org
                            or conn_names.get(acct.get("conn_id"))
                            or "Bank"
                        )

                    successes.append((url, accounts))
                except httpx.HTTPStatusError as e:
                    logger.warning(f"[SimpleFIN] {masked} failed ({e.response.status_code}): {e.response.text}")
                    errors.append({
                        "id": connection_id(url),
                        "label": masked,
                        "error": f"Auth failed ({e.response.status_code})",
                    })
                except Exception as e:
                    logger.warning(f"[SimpleFIN] {masked} error: {e}")
                    errors.append({
                        "id": connection_id(url),
                        "label": masked,
                        "error": str(e),
                    })

        return successes, errors
