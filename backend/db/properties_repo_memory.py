"""In-memory implementation of ``PropertiesRepo`` used by unit tests.

``install_for_tests()`` swaps the active repo on ``db.properties_repo`` to a
fresh ``InMemoryPropertiesRepo`` and returns it. Mirrors
``db/accounts_repo_memory.py`` so the two behave the same way in conftest.

The SQL semantics that tests actually depend on are reproduced faithfully:
deleting a property cascades into its valuations and rental terms but only
NULLs the ``property_id`` on its loans; ``add_valuation`` is upsert-by-day
and refreshes the denormalized ``current_value`` only when it is the newest
valuation on file.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from db import properties_repo


def _iso(value: Any) -> Any:
    """Match PgPropertiesRepo, which hands dates back as ISO strings."""
    return value.isoformat() if isinstance(value, date) else value


class InMemoryPropertiesRepo:
    """Dict-backed implementation of the ``PropertiesRepo`` Protocol."""

    def __init__(self) -> None:
        self.properties: Dict[str, Dict[str, Any]] = {}
        # property_id -> {as_of ISO string: valuation dict}
        self.valuations: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.loans: Dict[str, Dict[str, Any]] = {}
        # property_id -> list of unit dicts
        self.rental_terms: Dict[str, List[Dict[str, Any]]] = {}
        self._valuation_seq = 0

    def reset(self) -> None:
        self.properties.clear()
        self.valuations.clear()
        self.loans.clear()
        self.rental_terms.clear()
        self._valuation_seq = 0

    # -- properties ---------------------------------------------------------

    def list_properties(self) -> List[Dict[str, Any]]:
        return sorted(
            (dict(p) for p in self.properties.values()),
            key=lambda p: (p.get("name") or "").lower(),
        )

    def get_property(self, property_id: str) -> Optional[Dict[str, Any]]:
        found = self.properties.get(property_id)
        return dict(found) if found else None

    def upsert_property(self, property_row: Dict[str, Any]) -> Dict[str, Any]:
        pid = property_row["id"]
        existing = self.properties.get(pid, {})
        # Same server defaults the Pg repo applies, so the two agree on what a
        # sparsely-populated property looks like once stored.
        filled = properties_repo.apply_defaults(
            property_row, properties_repo.PROPERTY_DEFAULTS
        )
        row: Dict[str, Any] = {"id": pid}
        for field in properties_repo.PROPERTY_FIELDS:
            row[field] = _iso(filled.get(field))
        # current_value is owned by add_valuation once a valuation exists;
        # an upsert that omits it must not wipe it.
        if row.get("current_value") is None and existing.get("current_value") is not None:
            row["current_value"] = existing["current_value"]
        self.properties[pid] = row
        return dict(row)

    def delete_property(self, property_id: str) -> int:
        if property_id not in self.properties:
            return 0
        del self.properties[property_id]
        self.valuations.pop(property_id, None)      # ON DELETE CASCADE
        self.rental_terms.pop(property_id, None)    # ON DELETE CASCADE
        for loan in self.loans.values():            # ON DELETE SET NULL
            if loan.get("property_id") == property_id:
                loan["property_id"] = None
        return 1

    # -- valuations ---------------------------------------------------------

    def add_valuation(
        self,
        *,
        property_id: str,
        as_of: date,
        value: float,
        source: str = "manual",
        notes: str = "",
    ) -> None:
        key = _iso(as_of)
        by_day = self.valuations.setdefault(property_id, {})
        if key in by_day:
            by_day[key].update({"value": value, "source": source, "notes": notes or ""})
        else:
            self._valuation_seq += 1
            by_day[key] = {
                "id": self._valuation_seq,
                "property_id": property_id,
                "as_of": key,
                "value": value,
                "source": source,
                "notes": notes or "",
            }

        prop = self.properties.get(property_id)
        if prop is not None and by_day:
            newest = max(by_day)
            prop["current_value"] = by_day[newest]["value"]

    def list_valuations(self, property_id: str) -> List[Dict[str, Any]]:
        by_day = self.valuations.get(property_id, {})
        return [dict(by_day[k]) for k in sorted(by_day, reverse=True)]

    # -- loans --------------------------------------------------------------

    def list_loans(self, property_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = [
            dict(loan) for loan in self.loans.values()
            if property_id is None or loan.get("property_id") == property_id
        ]
        return sorted(
            rows,
            key=lambda r: (r.get("lien_position") or 1, (r.get("name") or "").lower()),
        )

    def get_loan(self, loan_id: str) -> Optional[Dict[str, Any]]:
        found = self.loans.get(loan_id)
        return dict(found) if found else None

    def upsert_loan(self, loan_row: Dict[str, Any]) -> Dict[str, Any]:
        lid = loan_row["id"]
        filled = properties_repo.apply_defaults(
            loan_row, properties_repo.LOAN_DEFAULTS
        )
        row: Dict[str, Any] = {"id": lid}
        for field in properties_repo.LOAN_FIELDS:
            row[field] = _iso(filled.get(field))
        self.loans[lid] = row
        return dict(row)

    def delete_loan(self, loan_id: str) -> int:
        return 1 if self.loans.pop(loan_id, None) is not None else 0

    # -- rental terms -------------------------------------------------------

    def list_rental_terms(self, property_id: str) -> List[Dict[str, Any]]:
        return [
            dict(t) for t in sorted(
                self.rental_terms.get(property_id, []),
                key=lambda t: t.get("unit_label") or "",
            )
        ]

    def replace_rental_terms(
        self, property_id: str, terms: List[Dict[str, Any]]
    ) -> None:
        self.rental_terms[property_id] = [
            {
                "property_id": property_id,
                "unit_label": t.get("unit_label") or "",
                "monthly_rent": t.get("monthly_rent") or 0,
                "lease_start": _iso(t.get("lease_start")),
                "lease_end": _iso(t.get("lease_end")),
                "tenant_name": t.get("tenant_name") or "",
                "notes": t.get("notes") or "",
            }
            for t in terms
        ]


_instance: Optional[InMemoryPropertiesRepo] = None


def install_for_tests() -> InMemoryPropertiesRepo:
    """Swap the active repo for a fresh in-memory one and return it."""
    global _instance
    _instance = InMemoryPropertiesRepo()
    properties_repo.set_repo(_instance)
    return _instance


def active() -> InMemoryPropertiesRepo:
    if _instance is None:
        raise RuntimeError(
            "InMemoryPropertiesRepo not installed; "
            "call install_for_tests() before reading state."
        )
    return _instance


def reset() -> None:
    """Clear the active in-memory repo. No-op if not installed."""
    if _instance is not None:
        _instance.reset()
