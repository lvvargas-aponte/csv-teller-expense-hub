"""seed_custom + seed_removed_defaults + allowlist_hosts

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-06 00:00:00.000000

Backs the runtime-editable seed list for the Knowledge tab.

* ``seed_custom``           — user-added seeds (URL imports they want
                              alongside the curated defaults).
* ``seed_removed_defaults`` — curated defaults the user has hidden;
                              keyed by the stable ``default_id`` baked
                              into ``backend/data/seeds_default.json``.
* ``allowlist_hosts``       — runtime additions to the SSRF allowlist.
                              When a user adds a custom seed, the host
                              is auto-inserted here; the URL fetcher
                              unions this with its base set.

The hardcoded base allowlist in ``url_fetcher.BASE_ALLOWED_HOSTS``
remains the trusted floor — runtime additions only ever expand the set,
never shrink it, so a misconfigured table can't lock you out of the
sites that ship with the app.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seed_custom",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("why", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "group_label",
            sa.String(60),
            server_default="Custom",
            nullable=False,
        ),
        sa.Column(
            "manual_only",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("url", name="uq_seed_custom_url"),
    )

    op.create_table(
        "seed_removed_defaults",
        # ``default_id`` is the stable identifier baked into
        # ``seeds_default.json`` (e.g. ``"d:irs-pub-17"``).  We don't FK
        # to anything because defaults live in a JSON file, not a table.
        sa.Column("default_id", sa.String(80), primary_key=True),
        sa.Column(
            "removed_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "allowlist_hosts",
        sa.Column("host", sa.String(255), primary_key=True),
        sa.Column(
            "added_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Where the host came from — 'custom_seed' (auto-added when a
        # user added a seed) vs 'manual' (added directly via API).  Lets
        # us garbage-collect later if we ever auto-prune unused hosts.
        sa.Column(
            "origin",
            sa.String(20),
            server_default="custom_seed",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("allowlist_hosts")
    op.drop_table("seed_removed_defaults")
    op.drop_table("seed_custom")
