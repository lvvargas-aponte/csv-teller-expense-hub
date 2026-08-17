"""peers: one row per person_slot

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-17 00:00:00.000000

A peer's real user_id is generated on their own instance and reaches us through
the sheet's Owner column, so bootstrap has to invent a placeholder. Without a
unique slot, adopting the real id would leave the placeholder behind as a second
row for the same person and peer_user_id() would pick between them arbitrarily.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # An instance that already accumulated two peers at one slot is exactly the
    # instance this constraint is for; without the dedupe the whole upgrade
    # chain would abort at container start.
    op.execute(
        """
        DELETE FROM peers p
        USING peers q
        WHERE p.person_slot = q.person_slot
          AND p.user_id <> q.user_id
          AND (p.added_at, p.user_id) < (q.added_at, q.user_id)
        """
    )
    op.create_unique_constraint("peers_person_slot_key", "peers", ["person_slot"])


def downgrade() -> None:
    op.drop_constraint("peers_person_slot_key", "peers", type_="unique")
