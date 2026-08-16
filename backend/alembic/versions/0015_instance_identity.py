"""instance_identity + peers — who this instance belongs to, and who it settles with

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-16 00:00:00.000000

``instance_identity`` is a singleton: the ``id = 1`` check constraint makes a
second row impossible. ``person_slot`` binds this instance to one of the two
existing ``person_1_owes`` / ``person_2_owes`` transaction fields, which are
globally stable across both instances.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instance_identity",
        sa.Column("id", sa.SmallInteger(), primary_key=True, server_default="1"),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False, unique=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("person_slot", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="instance_identity_singleton_check"),
        sa.CheckConstraint("person_slot IN (1, 2)", name="instance_identity_slot_check"),
    )
    op.create_table(
        "peers",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("person_slot", sa.SmallInteger(), nullable=False),
        sa.Column(
            "added_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("person_slot IN (1, 2)", name="peers_slot_check"),
    )


def downgrade() -> None:
    op.drop_table("peers")
    op.drop_table("instance_identity")
