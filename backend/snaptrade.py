"""
SnapTradeClient — all SnapTrade API interaction lives here.

SnapTrade aggregates brokerage + crypto accounts (Robinhood, M1, E-trade, ...)
and returns per-position holdings with current market value and average
purchase price.  Modeled on ``TellerClient``: route handlers call methods on
the module-level ``snaptrade`` instance (created in ``state.py``) and never
touch the SnapTrade SDK directly.

Auth model: one household-level ``(user_id, user_secret)`` pair, registered
once and persisted in the ``snaptrade_creds`` PgStore.  The SnapTrade
``client_id`` / ``consumer_key`` are app-level credentials read from config.

The SnapTrade SDK is synchronous; every call is wrapped in ``asyncio.to_thread``
so handlers keep the app's async contract.

Mocking in tests: patch async methods on the instance, e.g.
    patch.object(state.snaptrade, "get_all_holdings", AsyncMock(return_value=[...]))
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# SnapTrade universal-symbol type codes that represent equity-like instruments.
_EQUITY_TYPE_CODES = {"cs", "ad", "ps", "oef", "cef", "stock"}


# ---------------------------------------------------------------------------
# Pure parsing helpers — turn SnapTrade's deeply-nested payloads into the flat
# dict shape the ``holdings`` table expects.
# ---------------------------------------------------------------------------

def _dig(obj: Any, *keys: str) -> Optional[Any]:
    """Walk a chain of dict keys, returning None if any link is missing."""
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _num(value: Any) -> Optional[float]:
    """Coerce to float; return None when the value is missing or non-numeric."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _asset_type(type_code: Optional[str]) -> str:
    """Map a SnapTrade symbol type code to a holdings ``asset_type`` value."""
    code = (type_code or "").lower()
    if code == "crypto":
        return "crypto"
    if code in ("et", "etf"):
        return "etf"
    if code in _EQUITY_TYPE_CODES:
        return "stock"
    return "other"


def _parse_position(pos: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize one SnapTrade position into a ``holdings`` row dict.

    Returns None when the position has no resolvable ticker so a single
    malformed entry never aborts the whole sync.
    """
    sym = _dig(pos, "symbol", "symbol") or {}
    ticker = sym.get("symbol") or sym.get("raw_symbol")
    if not ticker:
        return None
    units = _num(pos.get("units")) or _num(pos.get("fractional_units")) or 0.0
    price = _num(pos.get("price"))
    avg_cost = _num(pos.get("average_purchase_price"))
    market_value = round(units * price, 2) if price is not None else None
    return {
        "symbol": str(ticker),
        "description": sym.get("description") or "",
        "asset_type": _asset_type(_dig(sym, "type", "code")),
        "quantity": units,
        "average_purchase_price": avg_cost,
        "last_price": price,
        "market_value": market_value,
        "currency": _dig(sym, "currency", "code") or "USD",
    }


def _normalize_account_holdings(item: Dict[str, Any]) -> Dict[str, Any]:
    """Turn one ``get_all_user_holdings`` element into ``{account, holdings,
    total_value, currency}``."""
    account = dict(item.get("account") or {})
    holdings = [
        h for h in (_parse_position(dict(p)) for p in (item.get("positions") or [])) if h
    ]
    total = _num(_dig(item, "total_value", "value"))
    if total is None:
        total = round(sum(h["market_value"] or 0.0 for h in holdings), 2)
    return {
        "account": {
            "id": account.get("id"),
            "name": account.get("name") or "Investment account",
            "institution": account.get("institution_name") or "",
            "number": account.get("number") or "",
        },
        "holdings": holdings,
        "total_value": total,
        "currency": _dig(item, "total_value", "currency") or "USD",
    }


# ---------------------------------------------------------------------------
# SnapTradeClient
# ---------------------------------------------------------------------------

class SnapTradeClient:
    """Encapsulates all SnapTrade API calls.

    Constructor args:
        client_id     — SnapTrade app client id (from config)
        consumer_key  — SnapTrade app consumer key (from config)

    SnapTrade has no sandbox/production switch — these two credentials are
    the entire auth surface. When either is unset the client is inert:
    ``configured`` is False and any call raises ``RuntimeError`` — so the app
    boots and the Investments tab degrades gracefully without SnapTrade keys.
    """

    def __init__(
        self,
        client_id: Optional[str],
        consumer_key: Optional[str],
    ) -> None:
        self._sdk: Any = None
        if client_id and consumer_key:
            try:
                import os

                from snaptrade_client import SnapTrade
                from snaptrade_client.configuration import Configuration

                # The SDK warns "X is deprecated" on every call to several
                # account_information methods even when the replacement isn't
                # actionable for us (e.g. ``list_user_accounts``). Suppress at
                # the source so our logs stay readable. Errors still surface.
                logging.getLogger("snaptrade_client").setLevel(logging.ERROR)

                # The SDK hardcodes certifi's bundle for ca_certs unless
                # ``ssl_ca_cert`` is set explicitly — it ignores REQUESTS_CA_BUNDLE
                # / SSL_CERT_FILE, so behind a TLS-inspecting proxy or antivirus
                # (e.g. Norton Web/Mail Shield) it fails cert verification even
                # though the rest of the app's outbound calls are fine. Point it
                # at the same merged system bundle the Dockerfile already builds.
                config = Configuration(consumer_key=consumer_key, client_id=client_id)
                config.ssl_ca_cert = os.environ.get("REQUESTS_CA_BUNDLE") or config.ssl_ca_cert
                self._sdk = SnapTrade(configuration=config)
                logger.info("[SnapTrade] SDK initialized")
            except Exception as e:  # pragma: no cover - import/SDK failure path
                logger.warning(f"[SnapTrade] SDK init failed — integration disabled: {e}")
        else:
            logger.info("[SnapTrade] Not configured (no client_id / consumer_key)")

        # Personal API keys (client_id like "PERS-...") are already scoped to a
        # single SnapTrade user — there's no registerUser call and no separate
        # userId/userSecret. Commercial/partner keys manage many end users and
        # need both. Detect which mode we're in so every call below knows
        # whether to send household creds or omit them entirely.
        self.is_personal = bool(client_id) and client_id.strip().upper().startswith("PERS-")

    @property
    def configured(self) -> bool:
        """True when the SnapTrade SDK is ready to make calls."""
        return self._sdk is not None

    def _require(self) -> Any:
        if self._sdk is None:
            raise RuntimeError(
                "SnapTrade is not configured — set SNAPTRADE_CLIENT_ID and "
                "SNAPTRADE_CONSUMER_KEY."
            )
        return self._sdk

    def _creds(self, user_id: str, user_secret: str) -> Dict[str, str]:
        """User-identity kwargs for an SDK call: omitted for Personal keys
        (the key itself is the identity), passed through for Commercial keys."""
        if self.is_personal:
            return {}
        return {"user_id": user_id, "user_secret": user_secret}

    async def register_user(self, user_id: str) -> Dict[str, str]:
        """Register the household SnapTrade user; return ``{user_id, user_secret}``.

        Personal API keys skip registration entirely — SnapTrade rejects
        registerUser for them since the key already identifies one user.
        Raises so the caller can surface a registration failure to the user.
        """
        if self.is_personal:
            return {"user_id": "personal", "user_secret": "personal"}

        sdk = self._require()

        def _call() -> Dict[str, Any]:
            return dict(sdk.authentication.register_snap_trade_user(user_id=user_id).body)

        body = await asyncio.to_thread(_call)
        return {
            "user_id": body.get("userId") or user_id,
            "user_secret": body.get("userSecret") or "",
        }

    async def login_url(self, user_id: str, user_secret: str) -> str:
        """Return a SnapTrade connection-portal URL the UI opens in a popup."""
        sdk = self._require()

        def _call() -> Any:
            return sdk.authentication.login_snap_trade_user(**self._creds(user_id, user_secret)).body

        body = await asyncio.to_thread(_call)
        if isinstance(body, dict):
            return body.get("redirectURI") or body.get("redirect_uri") or ""
        return str(body or "")

    async def get_all_holdings(
        self, user_id: str, user_secret: str
    ) -> List[Dict[str, Any]]:
        """Return normalized holdings for every connected account.

        SnapTrade deprecated and removed ``get_all_user_holdings`` (HTTP 410).
        The replacement is per-account: list accounts, then fetch holdings for
        each.
        """
        sdk = self._require()

        def _list_accounts() -> Any:
            return sdk.account_information.list_user_accounts(**self._creds(user_id, user_secret)).body

        accounts = await asyncio.to_thread(_list_accounts)
        logger.info(f"[SnapTrade] list_user_accounts returned {len(accounts or [])} account(s)")
        results: List[Dict[str, Any]] = []
        for raw in accounts or []:
            account = dict(raw)
            account_id = account.get("id")
            if not account_id:
                logger.warning(f"[SnapTrade] skipping account with no id: name={account.get('name')!r}")
                continue
            logger.info(
                f"[SnapTrade] syncing account {account_id} "
                f"(name={account.get('name')!r}, institution={account.get('institution_name')!r})"
            )

            def _positions(aid: str = account_id) -> Any:
                return sdk.account_information.get_user_account_positions(
                    account_id=aid, **self._creds(user_id, user_secret)
                ).body

            def _balance(aid: str = account_id) -> Any:
                return sdk.account_information.get_user_account_balance(
                    account_id=aid, **self._creds(user_id, user_secret)
                ).body

            try:
                positions = await asyncio.to_thread(_positions)
            except Exception as e:
                logger.warning(f"[SnapTrade] positions fetch failed for {account_id}: {e}")
                continue
            logger.info(f"[SnapTrade]   {account_id}: {len(positions or [])} position(s)")
            try:
                balance = await asyncio.to_thread(_balance)
            except Exception as e:
                logger.warning(f"[SnapTrade] balance fetch failed for {account_id}: {e}")
                balance = None
            total_value = None
            for b in (balance or []):
                bd = dict(b)
                v = _num(_dig(bd, "cash") or _dig(bd, "amount"))
                if v is not None:
                    total_value = (total_value or 0.0) + v
            item: Dict[str, Any] = {
                "account": account,
                "positions": list(positions or []),
            }
            if total_value is not None:
                item["total_value"] = {"value": total_value}
            results.append(_normalize_account_holdings(item))
        return results

    async def get_account_holdings(
        self, user_id: str, user_secret: str, account_id: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch positions + balance for a single connected account.

        Returns the same normalized shape as one element of
        :meth:`get_all_holdings`, or ``None`` if the account isn't reachable.
        """
        sdk = self._require()

        def _list_accounts() -> Any:
            return sdk.account_information.list_user_accounts(**self._creds(user_id, user_secret)).body

        accounts = await asyncio.to_thread(_list_accounts)
        match = next(
            (dict(a) for a in (accounts or []) if dict(a).get("id") == account_id),
            None,
        )
        if match is None:
            logger.warning(f"[SnapTrade] account {account_id} not found in user accounts")
            return None

        def _positions() -> Any:
            return sdk.account_information.get_user_account_positions(
                account_id=account_id, **self._creds(user_id, user_secret)
            ).body

        def _balance() -> Any:
            return sdk.account_information.get_user_account_balance(
                account_id=account_id, **self._creds(user_id, user_secret)
            ).body

        try:
            positions = await asyncio.to_thread(_positions)
        except Exception as e:
            logger.warning(f"[SnapTrade] positions fetch failed for {account_id}: {e}")
            return None
        try:
            balance = await asyncio.to_thread(_balance)
        except Exception as e:
            logger.warning(f"[SnapTrade] balance fetch failed for {account_id}: {e}")
            balance = None

        total_value = None
        for b in (balance or []):
            bd = dict(b)
            v = _num(_dig(bd, "cash") or _dig(bd, "amount"))
            if v is not None:
                total_value = (total_value or 0.0) + v

        item: Dict[str, Any] = {
            "account": match,
            "positions": list(positions or []),
        }
        if total_value is not None:
            item["total_value"] = {"value": total_value}
        return _normalize_account_holdings(item)

    async def list_connections(
        self, user_id: str, user_secret: str
    ) -> List[Dict[str, Any]]:
        """List the household's connected brokerages. Never raises."""
        sdk = self._require()

        def _call() -> Any:
            return sdk.connections.list_brokerage_authorizations(**self._creds(user_id, user_secret)).body

        try:
            body = await asyncio.to_thread(_call)
        except Exception as e:
            logger.warning(f"[SnapTrade] list_connections failed: {e}")
            return []
        out: List[Dict[str, Any]] = []
        for raw in body or []:
            c = dict(raw)
            out.append(
                {
                    "id": c.get("id"),
                    "brokerage": _dig(c, "brokerage", "name") or "Brokerage",
                    "disabled": bool(c.get("disabled")),
                    "created_date": c.get("created_date"),
                }
            )
        return out

    async def remove_connection(
        self, user_id: str, user_secret: str, authorization_id: str
    ) -> bool:
        """Remove one brokerage connection. Returns False on failure."""
        sdk = self._require()

        def _call() -> bool:
            sdk.connections.remove_brokerage_authorization(
                authorization_id=authorization_id, **self._creds(user_id, user_secret)
            )
            return True

        try:
            return await asyncio.to_thread(_call)
        except Exception as e:
            logger.warning(f"[SnapTrade] remove_connection failed: {e}")
            return False
