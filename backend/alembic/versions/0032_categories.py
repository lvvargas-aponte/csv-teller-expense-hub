"""categories — a category becomes a row you can rename, merge and archive

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-05 00:00:00.000000

A category was never stored anywhere. ``GET /api/categories`` computed the
list at read time from the distinct strings on transactions, the budget
keys, and a built-in default list, so there was nothing to edit: renaming
meant rewriting every transaction by hand, and merging two labels the same
import had spelled two ways meant editing a dict in ``category_normalizer``
and redeploying.

``roles`` is the other half. Five constants in ``analytics.py`` and one in
``routers/subscriptions.py`` compared lowercase category *names* to decide
whether a merchant is a bill, a subscription, or not spending at all — so
renaming "Subscriptions" would have silently changed recurring detection
with no error anywhere. Those sets move onto the row: rename it and the
behavior follows, because the behavior is attached to the row and not to
the spelling.

Roles are a set rather than one value because they genuinely overlap —
"Subscriptions" is always-recurring *and* a bill *and* a subscription.

Seeded from what is already in use: every distinct category on a
transaction, every budget key, and the categorizer's built-in defaults.
Names are compared case-insensitively; the first spelling seen wins, which
matches how ``known_categories`` picked one before.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirrors of the constants this migration is retiring. Copied rather than
# imported: a migration has to keep meaning what it meant when it ran, and
# the modules it would import are about to stop defining these.
_ALWAYS_RECURRING = {
    "utilities", "insurance", "rent", "mortgage", "phone", "internet",
    "subscription", "subscriptions",
}
_NON_SPENDING = {
    "cc payment", "credit card payment", "payments and credits",
    "zelle out", "transfer", "transfers",
}
_SUBSCRIPTION = {
    "subscription", "subscriptions", "entertainment", "streaming", "music",
}
_BILL = _ALWAYS_RECURRING | {"loan", "loans", "childcare"}
_NON_COMMITMENT = {"interest", "fees"}

# The categorizer's built-in seed list, so a fresh install still offers a
# usable set before anything has been imported.
_DEFAULTS = [
    "Groceries", "Dining", "Gas", "Utilities", "Rent", "Subscriptions",
    "Health", "Travel", "Shopping", "Entertainment", "Transport",
    "Insurance", "Income", "Fees", "Other",
]


def _roles_for(name: str) -> list:
    lowered = name.strip().lower()
    roles = []
    if lowered in _NON_SPENDING:
        roles.append("non_spending")
    if lowered in _ALWAYS_RECURRING:
        roles.append("always_recurring")
    if lowered in _BILL:
        roles.append("bill")
    if lowered in _SUBSCRIPTION:
        roles.append("subscription")
    if lowered in _NON_COMMITMENT:
        roles.append("non_commitment")
    return roles


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column(
            "roles",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "archived", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Case-insensitive uniqueness: "Dining" and "dining" are one category, and
    # letting both exist is how the label set forked in the first place.
    op.execute(
        "CREATE UNIQUE INDEX ix_categories_name_lower ON categories (lower(name))"
    )

    conn = op.get_bind()

    # Distinct labels already in use. Transactions and budgets are jsonb rows
    # in json_stores, not the ORM tables.
    used = conn.execute(
        sa.text(
            "SELECT DISTINCT trim(data->>'category') AS name FROM json_stores "
            "WHERE store_name = 'transactions' "
            "AND coalesce(trim(data->>'category'), '') <> ''"
        )
    ).fetchall()
    budget_keys = conn.execute(
        sa.text(
            "SELECT DISTINCT trim(key) AS name FROM json_stores "
            "WHERE store_name = 'budgets' AND coalesce(trim(key), '') <> ''"
        )
    ).fetchall()

    seen: dict = {}
    for row in list(used) + list(budget_keys):
        name = (row[0] or "").strip()
        if name and name.lower() not in seen:
            seen[name.lower()] = name
    for name in _DEFAULTS:
        if name.lower() not in seen:
            seen[name.lower()] = name

    for sort, name in enumerate(sorted(seen.values(), key=str.lower)):
        conn.execute(
            sa.text(
                "INSERT INTO categories (name, roles, sort) "
                "VALUES (:name, :roles, :sort)"
            ),
            {"name": name, "roles": _roles_for(name), "sort": sort},
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_categories_name_lower")
    op.drop_table("categories")
