"""Repository for the structured ``accounts`` + ``balance_snapshots`` tables.

The Postgres-backed implementation lives in ``PgAccountsRepo``; the
in-memory implementation used by unit tests lives in
``db.accounts_repo_memory.InMemoryAccountsRepo``. Both satisfy the
``AccountsRepo`` Protocol so callers can depend on the abstraction and
swap the backing store via ``set_repo()``.
"""
import json
from typing import Any, Dict, List, Optional, Protocol

from sqlalchemy import text

from db.base import sync_engine


class AccountsRepo(Protocol):
    """Public surface — the four operations every backing store implements."""

    def upsert_teller_account(self, account: Dict[str, Any]) -> None: ...

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


def _enrollment_id(account: Dict[str, Any]) -> Optional[str]:
    enrollment = account.get("enrollment")
    if isinstance(enrollment, dict):
        return enrollment.get("id")
    return None


class PgAccountsRepo:
    """Postgres-backed implementation. Default in production.

    Phase 4 added the Teller-account upsert. Phase 5 added the manual-account
    upsert and the balance-snapshot append so every balance refresh
    (Teller sync OR manual edit) contributes a row to the timeseries the
    dashboards chart from.
    """

    def upsert_teller_account(self, account: Dict[str, Any]) -> None:
        """Insert or update one row in ``accounts`` for a Teller account dict.

        The dict is shaped the way Teller's ``GET /accounts`` response delivers
        it: ``id``, ``name``, ``type``, ``subtype``, nested ``institution.name``
        and optional nested ``enrollment.id``.
        """
        institution = (account.get("institution") or {}).get("name", "") or ""
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO accounts ("
                    "  id, source, institution, name, type, subtype, manual, token_enrollment_id"
                    ") VALUES ("
                    "  :id, 'teller', :institution, :name, :type, :subtype, false, :enrollment"
                    ") "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "  institution = EXCLUDED.institution, "
                    "  name = EXCLUDED.name, "
                    "  type = EXCLUDED.type, "
                    "  subtype = EXCLUDED.subtype, "
                    "  token_enrollment_id = EXCLUDED.token_enrollment_id, "
                    "  updated_at = NOW()"
                ),
                {
                    "id": account["id"],
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

        ``source`` is one of ``'teller'``, ``'manual'``, ``'csv'``, or
        ``'override'`` (a user-supplied value that supersedes a Teller-reported
        balance). ``raw`` stores the original upstream payload as JSONB so
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