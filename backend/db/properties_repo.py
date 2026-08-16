"""Repository for the ``properties`` / ``property_valuations`` / ``loans`` /
``rental_terms`` tables.

Deliberately mirrors ``db/accounts_repo.py``: a ``PropertiesRepo`` Protocol,
a Postgres implementation, an in-memory twin in
``db/properties_repo_memory.py``, and ``get_repo()`` / ``set_repo()`` so the
no-database ``tests_unit`` suite can swap the backing store wholesale.

Synchronous on purpose. ``analytics.py`` and ``properties.py`` are plain
``def`` functions, and ``compute_goal_statuses()`` already reaches the
structured tables this way via ``accounts_repo.get_repo()``. Making these
async would force every caller up the chain to change colour.

Money crosses the boundary as ``float``. ``Numeric`` columns come back as
``Decimal``; converting here keeps Decimal out of ``analytics.py``, matching
what ``accounts_repo._row_to_holding`` already does.
"""
import json
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Protocol

from sqlalchemy import text

from db.base import sync_engine


class PropertiesRepo(Protocol):
    """Public surface — the operations every backing store implements."""

    def list_properties(self) -> List[Dict[str, Any]]: ...

    def get_property(self, property_id: str) -> Optional[Dict[str, Any]]: ...

    def upsert_property(self, property_row: Dict[str, Any]) -> Dict[str, Any]: ...

    def delete_property(self, property_id: str) -> int: ...

    def add_valuation(
        self,
        *,
        property_id: str,
        as_of: date,
        value: float,
        source: str = "manual",
        notes: str = "",
    ) -> None: ...

    def list_valuations(self, property_id: str) -> List[Dict[str, Any]]: ...

    def list_loans(self, property_id: Optional[str] = None) -> List[Dict[str, Any]]: ...

    def get_loan(self, loan_id: str) -> Optional[Dict[str, Any]]: ...

    def upsert_loan(self, loan_row: Dict[str, Any]) -> Dict[str, Any]: ...

    def delete_loan(self, loan_id: str) -> int: ...

    def list_rental_terms(self, property_id: str) -> List[Dict[str, Any]]: ...

    def replace_rental_terms(
        self, property_id: str, terms: List[Dict[str, Any]]
    ) -> None: ...


# ---------------------------------------------------------------------------
# Column definitions — single source of truth for INSERT/UPDATE/SELECT so the
# three statements can't drift apart as fields are added.
# ---------------------------------------------------------------------------

PROPERTY_FIELDS = (
    "name", "address", "property_type", "status", "units",
    "purchase_date", "purchase_price", "closing_costs", "capital_improvements",
    "current_value", "monthly_rent", "other_monthly_income", "vacancy_rate_pct",
    "property_tax_annual", "insurance_annual", "hoa_monthly", "utilities_monthly",
    "other_monthly_expense", "mgmt_fee_pct", "maintenance_pct_of_rent",
    "capex_reserve_pct_of_rent", "appreciation_pct", "rent_growth_pct",
    "rules", "operating_account_id", "notes",
)

LOAN_FIELDS = (
    "name", "loan_type", "property_id", "account_id", "lender", "lien_position",
    "original_principal", "current_principal", "interest_rate_pct", "rate_type",
    "term_months", "origination_date", "first_payment_date", "payment_day",
    "payment_amount", "escrow_monthly", "pmi_monthly", "extra_monthly",
    "io_months", "balloon_date", "notes",
)

# Server defaults, restated in Python.
#
# A column with a server default is still NOT NULL, and a server default only
# fires when the column is OMITTED from the INSERT — passing an explicit NULL
# raises NotNullViolation. Since the upsert writes every column by name, the
# defaults have to be applied here. Restating them is a drift risk, but a
# mismatch fails loudly against Postgres rather than corrupting data, and
# tests/test_properties_repo.py exercises exactly that path.
#
# Columns absent from these maps are genuinely nullable, where NULL is
# meaningful: "no purchase price on record" is different from zero, and
# appreciation_pct = NULL means "use the household assumption".
PROPERTY_DEFAULTS: Dict[str, Any] = {
    "address": "",
    "property_type": "single_family",
    "status": "rental",
    "units": 1,
    "closing_costs": 0,
    "capital_improvements": 0,
    "monthly_rent": 0,
    "other_monthly_income": 0,
    "vacancy_rate_pct": 5,
    "property_tax_annual": 0,
    "insurance_annual": 0,
    "hoa_monthly": 0,
    "utilities_monthly": 0,
    "other_monthly_expense": 0,
    "mgmt_fee_pct": 0,
    "maintenance_pct_of_rent": 5,
    "capex_reserve_pct_of_rent": 5,
    "rules": [],
    "notes": "",
}

LOAN_DEFAULTS: Dict[str, Any] = {
    "loan_type": "mortgage",
    "lender": "",
    "lien_position": 1,
    "rate_type": "fixed",
    "escrow_monthly": 0,
    "pmi_monthly": 0,
    "extra_monthly": 0,
    "io_months": 0,
    "notes": "",
}

# Written as JSONB; needs an explicit cast in the placeholder.
_JSONB_FIELDS = frozenset({"rules"})


def apply_defaults(row: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Fill None/missing values on NOT NULL columns with their server default."""
    out = dict(row)
    for field, default in defaults.items():
        if out.get(field) is None:
            out[field] = default
    return out

_MONEY_FIELDS = frozenset({
    "purchase_price", "closing_costs", "capital_improvements", "current_value",
    "monthly_rent", "other_monthly_income", "vacancy_rate_pct",
    "property_tax_annual", "insurance_annual", "hoa_monthly", "utilities_monthly",
    "other_monthly_expense", "mgmt_fee_pct", "maintenance_pct_of_rent",
    "capex_reserve_pct_of_rent", "appreciation_pct", "rent_growth_pct",
    "original_principal", "current_principal", "interest_rate_pct",
    "payment_amount", "escrow_monthly", "pmi_monthly", "extra_monthly",
    "value",
})


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Map a result row to a plain dict, Decimal -> float, dates -> ISO strings.

    Callers (routers, analytics, the amortization engine) all speak float and
    ISO strings; keeping the conversion here means none of them have to.
    """
    out: Dict[str, Any] = {}
    for key, value in dict(row._mapping).items():
        if isinstance(value, Decimal):
            out[key] = float(value)
        elif isinstance(value, date):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


class PgPropertiesRepo:
    """Postgres-backed implementation. Default in production."""

    # -- properties ---------------------------------------------------------

    def list_properties(self) -> List[Dict[str, Any]]:
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT * FROM properties ORDER BY name")
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_property(self, property_id: str) -> Optional[Dict[str, Any]]:
        with sync_engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM properties WHERE id = :id"), {"id": property_id}
            ).fetchone()
        return _row_to_dict(row) if row else None

    def upsert_property(self, property_row: Dict[str, Any]) -> Dict[str, Any]:
        return self._upsert(
            "properties", PROPERTY_FIELDS, PROPERTY_DEFAULTS, property_row
        )

    @staticmethod
    def _upsert(
        table: str,
        fields: tuple,
        defaults: Dict[str, Any],
        row: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Shared INSERT ... ON CONFLICT DO UPDATE for properties and loans."""
        filled = apply_defaults(row, defaults)
        params: Dict[str, Any] = {"id": filled["id"]}
        for field in fields:
            value = filled.get(field)
            params[field] = json.dumps(value) if field in _JSONB_FIELDS else value

        all_columns = ("id",) + fields
        columns = ", ".join(all_columns)
        # CAST(:x AS jsonb), not :x::jsonb — SQLAlchemy's text() treats the
        # colons in a `::` cast as parameter syntax and leaves the bind
        # unresolved, which Postgres then rejects as a syntax error.
        placeholders = ", ".join(
            f"CAST(:{c} AS jsonb)" if c in _JSONB_FIELDS else f":{c}"
            for c in all_columns
        )
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in fields)

        with sync_engine.begin() as conn:
            result = conn.execute(
                text(
                    f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
                    f"ON CONFLICT (id) DO UPDATE SET {updates}, updated_at = NOW() "
                    f"RETURNING *"
                ),
                params,
            ).fetchone()
        return _row_to_dict(result)

    def delete_property(self, property_id: str) -> int:
        """Delete a property. Valuations and rental terms cascade; loans keep
        existing with ``property_id`` set to NULL so debt is never silently
        dropped along with the asset."""
        with sync_engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM properties WHERE id = :id"), {"id": property_id}
            )
        return result.rowcount or 0

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
        """Record a valuation and refresh the denormalized ``current_value``.

        Re-valuing the same day overwrites rather than accumulating
        near-duplicates. ``current_value`` is only moved forward when this is
        the newest valuation on file, so backfilling an old appraisal doesn't
        clobber a current number.
        """
        with sync_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO property_valuations "
                    "  (property_id, as_of, value, source, notes) "
                    "VALUES (:pid, :as_of, :value, :source, :notes) "
                    "ON CONFLICT (property_id, as_of) DO UPDATE SET "
                    "  value = EXCLUDED.value, "
                    "  source = EXCLUDED.source, "
                    "  notes = EXCLUDED.notes"
                ),
                {
                    "pid": property_id, "as_of": as_of, "value": value,
                    "source": source, "notes": notes or "",
                },
            )
            conn.execute(
                text(
                    "UPDATE properties SET current_value = ("
                    "  SELECT value FROM property_valuations "
                    "  WHERE property_id = :pid ORDER BY as_of DESC LIMIT 1"
                    "), updated_at = NOW() WHERE id = :pid"
                ),
                {"pid": property_id},
            )

    def list_valuations(self, property_id: str) -> List[Dict[str, Any]]:
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM property_valuations "
                    "WHERE property_id = :pid ORDER BY as_of DESC"
                ),
                {"pid": property_id},
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    # -- loans --------------------------------------------------------------

    def list_loans(self, property_id: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM loans"
        params: Dict[str, Any] = {}
        if property_id is not None:
            sql += " WHERE property_id = :pid"
            params["pid"] = property_id
        sql += " ORDER BY lien_position, name"
        with sync_engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_loan(self, loan_id: str) -> Optional[Dict[str, Any]]:
        with sync_engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM loans WHERE id = :id"), {"id": loan_id}
            ).fetchone()
        return _row_to_dict(row) if row else None

    def upsert_loan(self, loan_row: Dict[str, Any]) -> Dict[str, Any]:
        return self._upsert("loans", LOAN_FIELDS, LOAN_DEFAULTS, loan_row)

    def delete_loan(self, loan_id: str) -> int:
        with sync_engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM loans WHERE id = :id"), {"id": loan_id}
            )
        return result.rowcount or 0

    # -- rental terms -------------------------------------------------------

    def list_rental_terms(self, property_id: str) -> List[Dict[str, Any]]:
        with sync_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM rental_terms WHERE property_id = :pid "
                    "ORDER BY unit_label"
                ),
                {"pid": property_id},
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def replace_rental_terms(
        self, property_id: str, terms: List[Dict[str, Any]]
    ) -> None:
        """Wholesale replace a property's units.

        Replace rather than merge: the UI edits the whole rent roll at once,
        and a partial merge would leave deleted units behind.
        """
        with sync_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM rental_terms WHERE property_id = :pid"),
                {"pid": property_id},
            )
            for term in terms:
                conn.execute(
                    text(
                        "INSERT INTO rental_terms ("
                        "  property_id, unit_label, monthly_rent, lease_start, "
                        "  lease_end, tenant_name, notes"
                        ") VALUES ("
                        "  :pid, :unit_label, :monthly_rent, :lease_start, "
                        "  :lease_end, :tenant_name, :notes)"
                    ),
                    {
                        "pid": property_id,
                        "unit_label": term.get("unit_label") or "",
                        "monthly_rent": term.get("monthly_rent") or 0,
                        "lease_start": term.get("lease_start"),
                        "lease_end": term.get("lease_end"),
                        "tenant_name": term.get("tenant_name") or "",
                        "notes": term.get("notes") or "",
                    },
                )


# ---------------------------------------------------------------------------
# Active-repo accessor — callers go through this so unit tests can swap in
# an InMemoryPropertiesRepo without monkey-patching individual functions.
# ---------------------------------------------------------------------------

_repo: PropertiesRepo = PgPropertiesRepo()


def get_repo() -> PropertiesRepo:
    """Return the active repo. Call inside handler bodies, not at import
    time, so test-time swaps are visible per request."""
    return _repo


def set_repo(repo: PropertiesRepo) -> None:
    """Replace the active repo. ``properties_repo_memory.install_for_tests()``
    calls this from the unit-test conftest before any router runs."""
    global _repo
    _repo = repo
