"""Repository for the structured ``accounts`` + ``balance_snapshots`` tables.

The Postgres-backed implementation lives in ``PgAccountsRepo``; the
in-memory implementation used by unit tests lives in
``db.accounts_repo_memory.InMemoryAccountsRepo``. Both satisfy the
``AccountsRepo`` Protocol so callers can depend on the abstraction and
swap the backing store via ``set_repo()``.
"""
import json
from typing import Any, Dict, List, Optional, Protocol, Tuple

from sqlalchemy import text

from db.base import sync_engine


class AccountsRepo(Protocol):
    """Public surface — the operations every backing store implements."""

    def upsert_synced_account(
        self, account: Dict[str, Any], source: str = "simplefin"
    ) -> None: ...

    def upsert_manual_account(
        self,
        *,
        account_id: str,
        institution: str,
        name: str,
        type_: str,
        subtype: str = "",
        source: str = "manual",
    ) -> None: ...

    def delete_manual_account(self, account_id: str) -> int: ...

    def insert_balance_snapshot(
        self,
        *,
        account_id: str,
        source: str,
        available: Optional[float] = None,
        ledger: Optional[float] = None,
        raw: Optional[Dict[str, Any]] = None,
        captured_at: Optional[str] = None,
    ) -> None: ...

    def get_snapshots_since(self, days: int) -> List[Dict[str, Any]]: ...

    def replace_holdings(
        self, account_id: str, holdings: List[Dict[str, Any]]
    ) -> None: ...

    def get_holdings(self) -> List[Dict[str, Any]]: ...

    def get_holdings_for_account(self, account_id: str) -> List[Dict[str, Any]]: ...

    def set_cost_override(
        self, account_id: str, symbol: str, average_purchase_price: float
    ) -> None: ...

    def delete_cost_override(self, account_id: str, symbol: str) -> int: ...

    def get_cost_overrides(self) -> Dict[Tuple[str, str], float]: ...


def _enrollment_id(account: Dict[str, Any]) -> Optional[str]:
    enrollment = account.get("enrollment")
    if isinstance(enrollment, dict):
        return enrollment.get("id")
    return None


class PgAccountsRepo:
    """Postgres-backed implementation. Default in production.

    Phase 4 added the synced-account upsert. Phase 5 added the manual-account
    upsert and the balance-snapshot append so every balance refresh
    (SimpleFIN sync OR manual edit) contributes a row to the timeseries the
    dashboards chart from.
    """

    def upsert_synced_account(
        self, account: Dict[str, Any], source: str = "simplefin"
    ) -> None:
        """Insert or update one ``accounts`` row for a synced (non-manual) account.

        The dict is shaped the way a provider's accounts listing delivers it:
        ``id``, ``name``, ``type``, ``subtype``, nested ``institution.name``
        and optional nested ``enrollment.id``. The SnapTrade sync builds the
        same shape and passes ``source='snaptrade'`` — both flavors set
        ``manual=false`` because the balance is refreshed by sync, not typed.
        """
        institution = (account.get("institution") or {}).get("name", "") or ""
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts ("
                    "  id, source, institution, name, type, subtype, manual, token_enrollment_id"
                    ") VALUES ("
                    "  :id, :source, :institution, :name, :type, :subtype, false, :enrollment"
                    ") "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "  source = EXCLUDED.source, "
                    "  institution = EXCLUDED.institution, "
                    "  name = EXCLUDED.name, "
                    "  type = EXCLUDED.type, "
                    "  subtype = EXCLUDED.subtype, "
                    "  token_enrollment_id = EXCLUDED.token_enrollment_id, "
                    "  updated_at = NOW()"
                ),
                {
                    "id": account["id"],
                    "source": source,
                    "institution": institution,
                    "name": account.get("name", "") or "",
                    "type": account.get("type", "") or "",
                    "subtype": account.get("subtype", "") or "",
                    "enrollment": _enrollment_id(account),
                },
            )

    def upsert_manual_account(
        self,
        *,
        account_id: str,
        institution: str,
        name: str,
        type_: str,
        subtype: str = "",
        source: str = "manual",
    ) -> None:
        """Insert or update one row in ``accounts`` for a user-added account.

        ``source`` is ``'manual'`` for balance-only accounts the user typed in
        and ``'csv'`` for the synthesized account created during a CSV upload
        so its transactions have an FK target. Both flavors set ``manual=true``.
        """
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts ("
                    "  id, source, institution, name, type, subtype, manual, token_enrollment_id"
                    ") VALUES ("
                    "  :id, :source, :institution, :name, :type, :subtype, true, NULL"
                    ") "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "  institution = EXCLUDED.institution, "
                    "  name = EXCLUDED.name, "
                    "  type = EXCLUDED.type, "
                    "  subtype = EXCLUDED.subtype, "
                    "  updated_at = NOW()"
                ),
                {
                    "id": account_id,
                    "source": source,
                    "institution": institution or "",
                    "name": name or "",
                    "type": type_ or "",
                    "subtype": subtype or "",
                },
            )

    def delete_manual_account(self, account_id: str) -> int:
        """Remove a manual or csv-synth accounts row.

        Returns the number of rows deleted. Cascades: ``balance_snapshots`` and
        ``account_details`` rows for this account id are removed automatically
        (``ON DELETE CASCADE`` declared in ``0001_initial``). Transactions keep
        existing with ``account_id`` set to NULL (``ON DELETE SET NULL``).
        """
        with sync_engine.begin() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM accounts WHERE id = :id AND source IN ('manual', 'csv')"
                ),
                {"id": account_id},
            )
        return result.rowcount or 0

    def insert_balance_snapshot(
        self,
        *,
        account_id: str,
        source: str,
        available: Optional[float] = None,
        ledger: Optional[float] = None,
        raw: Optional[Dict[str, Any]] = None,
        captured_at: Optional[str] = None,
    ) -> None:
        """Append one row to ``balance_snapshots``.

        ``source`` is one of ``'simplefin'``, ``'manual'``, ``'csv'``, or
        ``'override'`` (a user-supplied value that supersedes a provider-
        reported balance). ``raw`` stores the original upstream payload as JSONB so
        future analyses can recover fields we don't break out into columns
        today.

        ``captured_at`` defaults to ``NOW()`` (server-side); pass an ISO8601
        string to backdate a snapshot to a specific statement date.
        """
        with sync_engine.begin() as conn:
            if captured_at is None:
                sql = (
                    "INSERT INTO balance_snapshots ("
                    "  account_id, source, available, ledger, raw"
                    ") VALUES ("
                    "  :account_id, :source, :available, :ledger, "
                    "  CAST(:raw AS JSONB)"
                    ")"
                )
                params = {
                    "account_id": account_id,
                    "source": source,
                    "available": available,
                    "ledger": ledger,
                    "raw": json.dumps(raw, default=str) if raw is not None else None,
                }
            else:
                sql = (
                    "INSERT INTO balance_snapshots ("
                    "  account_id, source, available, ledger, raw, captured_at"
                    ") VALUES ("
                    "  :account_id, :source, :available, :ledger, "
                    "  CAST(:raw AS JSONB), CAST(:captured_at AS TIMESTAMPTZ)"
                    ")"
                )
                params = {
                    "account_id": account_id,
                    "source": source,
                    "available": available,
                    "ledger": ledger,
                    "raw": json.dumps(raw, default=str) if raw is not None else None,
                    "captured_at": captured_at,
                }
            conn.execute(text(sql), params)

    def get_snapshots_since(self, days: int) -> List[Dict[str, Any]]:
        """Return every balance_snapshots row captured in the last ``days``
        days, joined with the owning account's type so the analytics layer
        can classify each row as cash / credit / investment without a
        second round-trip.

        Rows are returned newest-first. Callers (analytics.balance_trend)
        scan the list to find each account's latest snapshot at or before
        a target timestamp.
        """
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT bs.account_id, bs.captured_at, bs.available, "
                    "       bs.ledger, bs.source, a.type, a.subtype "
                    "FROM balance_snapshots bs "
                    "LEFT JOIN accounts a ON a.id = bs.account_id "
                    "WHERE bs.captured_at >= NOW() - make_interval(days => :days) "
                    "ORDER BY bs.captured_at DESC"
                ),
                {"days": int(days)},
            ).fetchall()
        return [
            {
                "account_id": r[0],
                "captured_at": r[1],
                "available": float(r[2]) if r[2] is not None else None,
                "ledger": float(r[3]) if r[3] is not None else None,
                "source": r[4],
                "type": r[5] or "",
                "subtype": r[6] or "",
            }
            for r in rows
        ]

    # ── holdings (investment positions) ──────────────────────────────────────

    def replace_holdings(
        self, account_id: str, holdings: List[Dict[str, Any]]
    ) -> None:
        """Replace an account's holdings with the current position set.

        SnapTrade hands back the full current snapshot every sync, so the
        whole account is wiped and re-inserted in one transaction — a position
        the user fully sold simply disappears.
        """
        with sync_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM holdings WHERE account_id = :aid"),
                {"aid": account_id},
            )
            if not holdings:
                return
            conn.execute(
                text(
                    "INSERT INTO holdings ("
                    "  account_id, symbol, description, asset_type, quantity, "
                    "  average_purchase_price, last_price, market_value, currency"
                    ") VALUES ("
                    "  :account_id, :symbol, :description, :asset_type, :quantity, "
                    "  :average_purchase_price, :last_price, :market_value, :currency"
                    ")"
                ),
                [
                    {
                        "account_id": account_id,
                        "symbol": h["symbol"],
                        "description": h.get("description", "") or "",
                        "asset_type": h.get("asset_type", "other") or "other",
                        "quantity": h.get("quantity", 0) or 0,
                        "average_purchase_price": h.get("average_purchase_price"),
                        "last_price": h.get("last_price"),
                        "market_value": h.get("market_value"),
                        "currency": h.get("currency", "USD") or "USD",
                    }
                    for h in holdings
                ],
            )

    _HOLDINGS_SELECT = (
        "SELECT h.account_id, h.symbol, h.description, h.asset_type, "
        "       h.quantity, h.average_purchase_price, h.last_price, "
        "       h.market_value, h.currency, a.name, a.institution "
        "FROM holdings h "
        "LEFT JOIN accounts a ON a.id = h.account_id"
    )
    _HOLDINGS_ORDER = " ORDER BY h.market_value DESC NULLS LAST"

    @staticmethod
    def _row_to_holding(r: Any) -> Dict[str, Any]:
        return {
            "account_id": r[0],
            "symbol": r[1],
            "description": r[2] or "",
            "asset_type": r[3],
            "quantity": float(r[4]) if r[4] is not None else 0.0,
            "average_purchase_price": float(r[5]) if r[5] is not None else None,
            "last_price": float(r[6]) if r[6] is not None else None,
            "market_value": float(r[7]) if r[7] is not None else None,
            "currency": r[8] or "USD",
            "account_name": r[9] or "",
            "institution": r[10] or "",
        }

    def get_holdings(self) -> List[Dict[str, Any]]:
        """Every holding across all accounts, joined with account name/institution."""
        with sync_engine.connect() as conn:
            rows = conn.execute(text(self._HOLDINGS_SELECT + self._HOLDINGS_ORDER)).fetchall()
        return [self._row_to_holding(r) for r in rows]

    def get_holdings_for_account(self, account_id: str) -> List[Dict[str, Any]]:
        """Holdings for one account."""
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text(self._HOLDINGS_SELECT + " WHERE h.account_id = :aid" + self._HOLDINGS_ORDER),
                {"aid": account_id},
            ).fetchall()
        return [self._row_to_holding(r) for r in rows]

    # ── cost-basis overrides ─────────────────────────────────────────────────

    def set_cost_override(
        self, account_id: str, symbol: str, average_purchase_price: float
    ) -> None:
        """Record the user's average cost for one position."""
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO holding_cost_overrides ("
                    "  account_id, symbol, average_purchase_price"
                    ") VALUES (:account_id, :symbol, :price) "
                    "ON CONFLICT (account_id, symbol) DO UPDATE SET "
                    "  average_purchase_price = EXCLUDED.average_purchase_price, "
                    "  updated_at = NOW()"
                ),
                {
                    "account_id": account_id,
                    "symbol": symbol,
                    "price": average_purchase_price,
                },
            )

    def delete_cost_override(self, account_id: str, symbol: str) -> int:
        with sync_engine.begin() as conn:
            result = conn.execute(
                text(
                    "DELETE FROM holding_cost_overrides "
                    "WHERE account_id = :account_id AND symbol = :symbol"
                ),
                {"account_id": account_id, "symbol": symbol},
            )
        return result.rowcount or 0

    def get_cost_overrides(self) -> Dict[Tuple[str, str], float]:
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT account_id, symbol, average_purchase_price "
                    "FROM holding_cost_overrides"
                )
            ).fetchall()
        return {(r[0], r[1]): float(r[2]) for r in rows}


# ---------------------------------------------------------------------------
# Active-repo accessor — routers go through this so unit tests can swap in
# an InMemoryAccountsRepo without monkey-patching individual functions.
# ---------------------------------------------------------------------------

_repo: AccountsRepo = PgAccountsRepo()


def get_repo() -> AccountsRepo:
    """Return the active repo. Routers call this inside handler bodies so
    test-time swaps are visible per request."""
    return _repo


def set_repo(repo: AccountsRepo) -> None:
    """Replace the active repo. ``InMemoryAccountsRepo.install()`` calls this
    from the unit-test conftest before any router is exercised."""
    global _repo
    _repo = repo