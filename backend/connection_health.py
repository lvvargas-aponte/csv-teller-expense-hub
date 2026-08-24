"""Per-institution connection health, recorded at sync time and read from cache.

Health used to be answered by asking the providers on every page load, which
made an aggregator round-trip the price of opening the Accounts tab. It is
instead a by-product of syncing: whichever path last talked to a provider
writes what it learned into the balances cache, and readers derive institution
status from that snapshot without any network call.

Two facts are recorded:

* ``simplefin_connections`` — per access URL, the institutions it served and
  when it last succeeded. SimpleFIN reports failures per access URL, not per
  institution, so without this mapping a failed URL could only be described as
  "some connection is broken".
* ``simplefin_connection_errors`` / ``snaptrade_disabled`` — what was failing
  as of that sync.

Status is one of ``connected`` / ``disconnected`` / ``manual``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from institution_normalizer import normalize as normalize_institution

CONNECTIONS_KEY = "simplefin_connections"
ERRORS_KEY = "simplefin_connection_errors"
SNAPTRADE_DISABLED_KEY = "snaptrade_disabled"


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _org_of(account: Dict[str, Any]) -> str:
    """Institution name for a raw SimpleFIN account.

    ``list_accounts_by_url`` has already resolved the v2 connections array (or
    an inline ``org``) onto ``_org_name``. Reading only that field keeps this
    identical to ``simplefin.iter_normalized_accounts``, so the institution
    recorded here always matches the one on the account rows it is joined to.
    """
    return account.get("_org_name") or ""


def record_simplefin_sync(
    url_batches: Iterable[Any],
    url_errors: Iterable[Dict[str, Any]],
) -> None:
    """Persist what a live SimpleFIN fetch just revealed about each connection.

    Institutions are remembered per connection so a later failure of that same
    connection can name the banks it covers — a failed URL returns no accounts,
    and therefore no institution names, of its own.
    """
    import state
    from simplefin import connection_id

    cache = state._balances_cache_store.data
    known: Dict[str, Any] = dict(cache.get(CONNECTIONS_KEY) or {})

    for url, accounts in url_batches:
        cid = connection_id(url)
        institutions = sorted({
            normalize_institution(_org_of(a)) for a in accounts if _org_of(a)
        })
        entry = dict(known.get(cid) or {})
        entry["institutions"] = institutions or entry.get("institutions") or []
        entry["last_ok"] = _now()
        known[cid] = entry

    errors = [dict(e) for e in url_errors]
    for err in errors:
        cid = err.get("id")
        if not cid:
            continue
        entry = dict(known.get(cid) or {})
        # Keep the institutions learned when this connection last worked.
        entry.setdefault("institutions", [])
        entry["label"] = err.get("label") or entry.get("label", "")
        known[cid] = entry

    cache[CONNECTIONS_KEY] = known
    cache[ERRORS_KEY] = [{**e, "at": _now()} for e in errors]
    state._balances_cache_store.save()


def record_snaptrade_connections(connections: Iterable[Dict[str, Any]]) -> None:
    """Persist which brokerages SnapTrade reports as disabled."""
    import state

    disabled = sorted({
        normalize_institution(c.get("brokerage"))
        for c in connections
        if c.get("disabled") and c.get("brokerage")
    })
    state._balances_cache_store.data[SNAPTRADE_DISABLED_KEY] = disabled
    state._balances_cache_store.save()


def broken_institutions() -> Dict[str, str]:
    """Institution -> error message, from the last sync that saw a failure."""
    import state

    cache = state._balances_cache or {}
    connections = cache.get(CONNECTIONS_KEY) or {}
    out: Dict[str, str] = {}

    for err in cache.get(ERRORS_KEY) or []:
        entry = connections.get(err.get("id")) or {}
        message = err.get("error") or "Connection failed"
        names = entry.get("institutions") or []
        if names:
            for name in names:
                out[name] = message
        else:
            # A connection that has never succeeded has no institutions to
            # attribute the failure to; surface it under its masked label so
            # the user still learns something broke.
            out[err.get("label") or "Unknown connection"] = message

    for name in cache.get(SNAPTRADE_DISABLED_KEY) or []:
        out[name] = "Brokerage authorization is disabled"

    return out


def build(accounts: Iterable[Any]) -> List[Dict[str, Any]]:
    """One health row per institution across ``accounts``.

    ``accounts`` are ``AccountBalance`` models from the summary. An institution
    is ``manual`` only when every account under it is manual — one synced
    account makes the institution a real connection.
    """
    broken = broken_institutions()
    by_name: Dict[str, Dict[str, Any]] = {}

    for a in accounts:
        name = a.institution
        if not name:
            continue
        entry = by_name.setdefault(name, {"institution": name, "all_manual": True})
        if not a.manual:
            entry["all_manual"] = False

    out: List[Dict[str, Any]] = []
    for name, entry in by_name.items():
        error: Optional[str] = broken.get(name)
        if entry["all_manual"]:
            status = "manual"
            error = None
        elif error:
            status = "disconnected"
        else:
            status = "connected"
        out.append({"institution": name, "status": status, "last_error": error})

    # A connection that failed before it ever returned an account has no row
    # above — it is named by its label instead, and must still be reported.
    for name, message in broken.items():
        if name not in by_name:
            out.append({"institution": name, "status": "disconnected", "last_error": message})

    return sorted(out, key=lambda c: c["institution"])
