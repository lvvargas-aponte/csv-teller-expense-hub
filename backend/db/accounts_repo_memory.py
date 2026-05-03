"""In-memory implementation of ``AccountsRepo`` used by unit tests.

``install_for_tests()`` swaps the active repo on ``db.accounts_repo`` to a
fresh ``InMemoryAccountsRepo`` and returns it. The module exposes
``active()`` so tests can read its state, and ``reset()`` so the autouse
conftest fixture can clear it between tests.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


class InMemoryAccountsRepo:
    """Dict-and-list backed implementation of the ``AccountsRepo`` Protocol.

    Mirrors the SQL semantics of ``PgAccountsRepo`` closely enough to satisfy
    the test assertions: ``delete_manual_account`` cascades into snapshots,
    ``upsert_*`` overwrites the same id, ``insert_balance_snapshot`` appends.
    The two attributes ``accounts`` and ``snapshots`` are public so tests can
    assert directly on what got recorded.
    """

    def __init__(self) -> None:
        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.snapshots: List[Dict[str, Any]] = []

    def upsert_teller_account(self, account: Dict[str, Any]) -> None:
        aid = account["id"]
        institution = (account.get("institution") or {}).get("name", "") or ""
        enrollment = account.get("enrollment") or {}
        self.accounts[aid] = {
            "id": aid,
            "source": "teller",
            "institution": institution,
            "name": account.get("name", "") or "",
            "type": account.get("type", "") or "",
            "subtype": account.get("subtype", "") or "",
            "manual": False,
            "token_enrollment_id": enrollment.get("id") if isinstance(enrollment, dict) else None,
        }

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
        self.accounts[account_id] = {
            "id": account_id,
            "source": source,
            "institution": institution or "",
            "name": name or "",
            "type": type_ or "",
            "subtype": subtype or "",
            "manual": True,
            "token_enrollment_id": None,
        }

    def delete_manual_account(self, account_id: str) -> int:
        record = self.accounts.get(account_id)
        if not record or record.get("source") not in ("manual", "csv"):
            return 0
        del self.accounts[account_id]
        # Cascade: matches the ON DELETE CASCADE declared on balance_snapshots.
        self.snapshots[:] = [s for s in self.snapshots if s["account_id"] != account_id]
        return 1

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
        self.snapshots.append({
            "account_id": account_id,
            "source": source,
            "available": available,
            "ledger": ledger,
            "raw": raw,
            "captured_at": captured_at,
        })

    def get_snapshots_since(self, days: int) -> List[Dict[str, Any]]:
        """Mirror of ``PgAccountsRepo.get_snapshots_since``.

        Filters by the snapshot's ``captured_at`` (parsed if a string,
        treated as ``now()`` if None — matches the SQL default) and joins
        the account's type/subtype the same way the SQL version does.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(days))
        out: List[Dict[str, Any]] = []
        for snap in self.snapshots:
            captured = snap.get("captured_at")
            if captured is None:
                ts = datetime.now(timezone.utc)
            elif isinstance(captured, datetime):
                ts = captured if captured.tzinfo else captured.replace(tzinfo=timezone.utc)
            else:
                try:
                    ts = datetime.fromisoformat(str(captured).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                continue
            account = self.accounts.get(snap["account_id"], {})
            out.append({
                "account_id": snap["account_id"],
                "captured_at": ts,
                "available": snap.get("available"),
                "ledger": snap.get("ledger"),
                "source": snap.get("source"),
                "type": account.get("type", "") or "",
                "subtype": account.get("subtype", "") or "",
            })
        out.sort(key=lambda r: r["captured_at"], reverse=True)
        return out

    def reset(self) -> None:
        self.accounts.clear()
        self.snapshots.clear()


# ---------------------------------------------------------------------------
# Test-only singleton helpers
# ---------------------------------------------------------------------------

_instance: Optional[InMemoryAccountsRepo] = None


def install_for_tests() -> InMemoryAccountsRepo:
    """Swap ``db.accounts_repo``'s active repo for a fresh in-memory one.

    Idempotent on calls within a single process — re-installing creates a
    new instance and rebinds the active repo, which is what the conftest
    wants between sessions if ever invoked twice.
    """
    from db.accounts_repo import set_repo

    global _instance
    _instance = InMemoryAccountsRepo()
    set_repo(_instance)
    return _instance


def active() -> InMemoryAccountsRepo:
    """Return the installed in-memory repo. Raises if ``install_for_tests``
    hasn't been called — that's a configuration bug, not a runtime error."""
    if _instance is None:
        raise RuntimeError(
            "InMemoryAccountsRepo not installed; "
            "call install_for_tests() before reading state."
        )
    return _instance


def reset() -> None:
    """Clear the active in-memory repo. No-op if not installed."""
    if _instance is not None:
        _instance.reset()


# ---------------------------------------------------------------------------
# Test introspection helpers — kept as module-level functions so existing
# tests that grew up before this refactor (``accounts_repo_memory.get_accounts()``)
# don't have to change.
# ---------------------------------------------------------------------------

def get_accounts() -> Dict[str, Dict[str, Any]]:
    return active().accounts


def get_snapshots() -> List[Dict[str, Any]]:
    return active().snapshots
