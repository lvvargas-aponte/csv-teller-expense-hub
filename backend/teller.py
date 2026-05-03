"""
TellerClient — all Teller.io HTTP interaction lives here.

Route handlers call methods on the module-level `teller` instance (created in
main.py) and never touch httpx or iterate over tokens themselves.

Mocking in tests: patch individual async methods on the instance, e.g.
    patch.object(main.teller, "list_accounts", AsyncMock(return_value=[...]))
"""
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException

from config import DEBUG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers (imported by main.py — no circular dependency)
# ---------------------------------------------------------------------------

def _mask_token(token: str) -> str:
    """Return a safely loggable representation of an access token."""
    return f"{token[:8]}...{token[-4:]}" if len(token) > 12 else "***"


def _detail(public_msg: str, debug_msg: str) -> str:
    """Return verbose debug detail in dev; a safe public message in production."""
    return debug_msg if DEBUG else public_msg


# ---------------------------------------------------------------------------
# TellerClient
# ---------------------------------------------------------------------------

class TellerClient:
    """Encapsulates all Teller.io API calls.

    Constructor args:
        tokens        — list of access tokens (shared reference from main.py,
                        so appends/removes in main stay visible here)
        base_url      — e.g. "https://api.teller.io"
        cert          — mTLS cert tuple (cert_path, key_path) or None
        max_tx_count  — hard cap on transactions fetched per account per call
    """

    def __init__(
        self,
        tokens: List[str],
        base_url: str,
        cert: Optional[Tuple[str, str]],
        max_tx_count: int = 500,
    ) -> None:
        self._tokens = tokens
        self._base_url = base_url
        self._cert = cert
        self._max_tx = max_tx_count
        self._enrollment_map: Dict[str, str] = {}  # enrollment_id → access_token
        # Stable, unambiguous id for each failing token so the frontend can
        # disconnect "Connection Error" rows without any risk of a mask
        # collision removing the wrong token from .env.  Rebuilt per token on
        # first reference in _error_entry.
        self._error_id_map: Dict[str, str] = {}    # error_id → access_token

    # ── Internal helpers ────────────────────────────────────────────────────

    def _http_client(self) -> httpx.AsyncClient:
        """Return a pre-configured httpx client (use as async context manager)."""
        kwargs: Dict[str, Any] = {"timeout": httpx.Timeout(30.0, connect=10.0)}
        if self._cert:
            kwargs["cert"] = self._cert
        return httpx.AsyncClient(**kwargs)

    def get_enrollment_id(self, token: str) -> Optional[str]:
        """Reverse-lookup: return the enrollment_id for a given access token."""
        return next(
            (eid for eid, tok in self._enrollment_map.items() if tok == token), None
        )

    def _error_id_for(self, token: str) -> str:
        """Return the stable error_id for a token, minting one on first use."""
        existing = next(
            (eid for eid, tok in self._error_id_map.items() if tok == token),
            None,
        )
        if existing:
            return existing
        new_id = f"_error_{uuid.uuid4().hex[:16]}"
        self._error_id_map[new_id] = token
        return new_id

    def pop_error_token(self, error_id: str) -> Optional[str]:
        """Remove and return the token a given _error_ id refers to."""
        return self._error_id_map.pop(error_id, None)

    def _error_entry(
        self, token: str, status_code: Optional[int] = None
    ) -> Dict[str, Any]:
        """Build a placeholder account dict for a token that failed."""
        return {
            "id": self._error_id_for(token),
            "name": "Unknown account",
            "type": "",
            "subtype": "",
            "institution": {"name": "—"},
            "balance": {},
            "_connection_error": True,
            "_error_status": status_code,
            "_enrollment_id": self.get_enrollment_id(token),
        }

    # ── Public API ───────────────────────────────────────────────────────────

    async def list_accounts(self) -> List[Dict[str, Any]]:
        """GET /accounts for every token.

        Deduplicates by account id and attaches ``_teller_token`` to each
        account.  Tokens that fail produce an error-placeholder entry so the
        frontend can surface the connection problem.
        """
        seen_ids: set = set()
        all_accounts: List[Dict[str, Any]] = []

        async with self._http_client() as client:
            for token in self._tokens:
                try:
                    resp = await client.get(
                        f"{self._base_url}/accounts", auth=(token, "")
                    )
                    resp.raise_for_status()
                    for acct in resp.json():
                        if acct["id"] not in seen_ids:
                            seen_ids.add(acct["id"])
                            acct["_teller_token"] = token
                            all_accounts.append(acct)
                except httpx.HTTPStatusError as e:
                    logger.warning(
                        f"[Teller] Token {_mask_token(token)} failed "
                        f"({e.response.status_code}): {e.response.text}"
                    )
                    all_accounts.append(self._error_entry(token, e.response.status_code))
                except Exception as e:
                    logger.warning(f"[Teller] Token {_mask_token(token)} error: {e}")
                    all_accounts.append(self._error_entry(token))

        return all_accounts

    async def list_transactions(
        self,
        account_id: str,
        count: int,
        tokens_to_try: List[str],
    ) -> List[Dict[str, Any]]:
        """GET /accounts/{id}/transactions.

        Tries each token in order.  Skips 401/403 (wrong token for account).
        Raises ``HTTPException`` for any other HTTP or connection error.
        """
        params = {"count": min(count, self._max_tx)}

        async with self._http_client() as client:
            for token in tokens_to_try:
                try:
                    resp = await client.get(
                        f"{self._base_url}/accounts/{account_id}/transactions",
                        auth=(token, ""),
                        params=params,
                    )
                    resp.raise_for_status()
                    return resp.json()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (401, 403):
                        continue
                    raise HTTPException(
                        status_code=e.response.status_code,
                        detail=_detail(
                            "Teller request failed.",
                            f"Failed to fetch transactions: {e.response.text}",
                        ),
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=500,
                        detail=_detail("Connection error.", f"Connection error: {str(e)}"),
                    )

        raise HTTPException(
            status_code=401,
            detail="No valid Teller token found for this account.",
        )

    async def get_balance(
        self,
        account_id: str,
        tokens_to_try: List[str],
    ) -> Dict[str, Any]:
        """GET /accounts/{id}/balances.

        Tries each token in order.  Skips 401/403.  Raises ``HTTPException``
        for any other error.
        """
        async with self._http_client() as client:
            for token in tokens_to_try:
                try:
                    resp = await client.get(
                        f"{self._base_url}/accounts/{account_id}/balances",
                        auth=(token, ""),
                    )
                    resp.raise_for_status()
                    return resp.json()
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (401, 403):
                        continue
                    raise HTTPException(
                        status_code=e.response.status_code,
                        detail=_detail(
                            "Teller request failed.",
                            f"Failed to fetch balance: {e.response.text}",
                        ),
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=500,
                        detail=_detail(
                            "Failed to fetch balance.",
                            f"Failed to fetch balance: {str(e)}",
                        ),
                    )

        raise HTTPException(
            status_code=401,
            detail="No valid Teller token found for this account.",
        )

    async def fetch_balance_safe(
        self, account_id: str, token: str
    ) -> Optional[Dict[str, Any]]:
        """GET /accounts/{id}/balances — never raises.

        Per the Teller API docs, the `/accounts` endpoint does NOT include
        balance data; it must be fetched per account.  Returns the balance
        dict ({"available": str|None, "ledger": str|None, ...}) or None on
        any failure so a single bad account does not abort the whole refresh.
        """
        async with self._http_client() as client:
            try:
                resp = await client.get(
                    f"{self._base_url}/accounts/{account_id}/balances",
                    auth=(token, ""),
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"[Teller] Balance fetch failed for {account_id} "
                    f"(token {_mask_token(token)}): {e.response.status_code}"
                )
                return None
            except Exception as e:
                logger.warning(
                    f"[Teller] Balance fetch errored for {account_id} "
                    f"(token {_mask_token(token)}): {e}"
                )
                return None

    async def list_accounts_by_token(
        self,
    ) -> Tuple[List[Tuple[str, List[Dict]]], List[Dict]]:
        """GET /accounts for each token individually.

        Returns ``(successes, error_dicts)`` where:
          - successes  — ``[(token, accounts_list), ...]`` for tokens that worked
          - error_dicts — ``[{"token": masked, "error": str}, ...]`` for failures

        Used by sync and balances-summary routes so they can associate each
        account with the token that owns it.
        """
        successes: List[Tuple[str, List[Dict]]] = []
        errors: List[Dict] = []

        async with self._http_client() as client:
            for token in self._tokens:
                masked = _mask_token(token)
                try:
                    resp = await client.get(
                        f"{self._base_url}/accounts", auth=(token, "")
                    )
                    resp.raise_for_status()
                    successes.append((token, resp.json()))
                except httpx.HTTPStatusError as e:
                    logger.warning(
                        f"[Teller] Token {masked} failed "
                        f"({e.response.status_code}): {e.response.text}"
                    )
                    errors.append(
                        {
                            "token": masked,
                            "error": f"Auth failed ({e.response.status_code}): {e.response.text}",
                        }
                    )
                except Exception as e:
                    logger.warning(f"[Teller] Token {masked} error: {e}")
                    errors.append({"token": masked, "error": str(e)})

        return successes, errors

    async def fetch_account_transactions(
        self,
        account_id: str,
        token: str,
        count: int,
    ) -> List[Dict[str, Any]]:
        """GET /accounts/{id}/transactions for a single known token.

        Does not catch exceptions — callers (sync route) catch them to record
        per-account error entries and extract ``teller-enrollment-status``.
        """
        async with self._http_client() as client:
            resp = await client.get(
                f"{self._base_url}/accounts/{account_id}/transactions",
                auth=(token, ""),
                params={"count": min(count, self._max_tx)},
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_account(self, account_id: str) -> bool:
        """DELETE /accounts/{id} across all tokens.

        Returns ``True`` if any token successfully deleted the account,
        ``False`` if no token was able to (caller raises 404).
        """
        async with self._http_client() as client:
            for token in self._tokens:
                try:
                    resp = await client.delete(
                        f"{self._base_url}/accounts/{account_id}",
                        auth=(token, ""),
                    )
                    if resp.status_code in (200, 204):
                        return True
                    if resp.status_code in (401, 403):
                        continue
                    resp.raise_for_status()
                except httpx.HTTPStatusError:
                    continue
                except Exception as e:
                    logger.warning(
                        f"[Teller] Error deleting account {account_id}: {e}"
                    )
                    continue

        return False
