"""The refusals. Pure — no I/O.

Each one refuses the entire sync rather than degrading to a partial run: a
half-synced month is worse than an unsynced one, because sub-project C would
then settle over partial data and the result would look plausible.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional

from sheet_sync.contract import CONTRACT_VERSION
from sheet_sync.engine import SheetRow


@dataclass(frozen=True)
class Claim:
    """One instance's row in the ``_sync`` worksheet: who it is, what it speaks."""

    user_id: str
    display_name: str
    person_slot: int
    contract_version: str
    person_1_name: str
    person_2_name: str


@dataclass(frozen=True)
class Refusal:
    reason: str
    message: str


def check_contract_version(mine: Claim, peers: List[Claim]) -> Optional[Refusal]:
    for peer in peers:
        if peer.contract_version == mine.contract_version:
            continue
        older = (
            peer.display_name
            if peer.contract_version < mine.contract_version
            else mine.display_name
        )
        return Refusal(
            "contract_version",
            f"Sync refused: this instance speaks sheet contract "
            f"{mine.contract_version}, but {peer.display_name}'s speaks "
            f"{peer.contract_version or '(none)'}. {older}'s instance must "
            f"update before the two can sync.",
        )
    return None


def check_person_names(mine: Claim, peers: List[Claim]) -> Optional[Refusal]:
    for peer in peers:
        if (peer.person_1_name, peer.person_2_name) == (
            mine.person_1_name,
            mine.person_2_name,
        ):
            continue
        return Refusal(
            "person_names",
            f"Sync refused: the two instances disagree about the person names "
            f"that title the owes columns. Here: "
            f"PERSON_1_NAME={mine.person_1_name!r}, PERSON_2_NAME={mine.person_2_name!r}. "
            f"On {peer.display_name}'s: "
            f"PERSON_1_NAME={peer.person_1_name!r}, PERSON_2_NAME={peer.person_2_name!r}. "
            f"Both must be identical.",
        )
    return None


def check_slot_collision(mine: Claim, peers: List[Claim]) -> Optional[Refusal]:
    for peer in peers:
        if peer.user_id == mine.user_id or peer.person_slot != mine.person_slot:
            continue
        return Refusal(
            "slot_collision",
            f"Sync refused: {mine.display_name} ({mine.user_id}) and "
            f"{peer.display_name} ({peer.user_id}) both claim person slot "
            f"{mine.person_slot}. Two instances cannot be the same person — one "
            f"must change INSTANCE_PERSON_SLOT. Every settlement would otherwise "
            f"be inverted on one side.",
        )
    return None


_CLAIM_CHECKS = (check_contract_version, check_person_names, check_slot_collision)


def check_claims(mine: Claim, peers: List[Claim]) -> Optional[Refusal]:
    """Run the instance-level guards in order, returning the first failure."""
    for check in _CLAIM_CHECKS:
        refusal = check(mine, peers)
        if refusal:
            return refusal
    return None


def check_duplicate_txn_ids(title: str, rows: List[SheetRow]) -> Optional[Refusal]:
    """Refuse when one worksheet carries a Txn ID twice.

    ``plan_push`` and ``plan_pull`` key on Txn ID, so a duplicate silently
    collapses: one row is maintained and the other becomes invisible to sync
    while still contributing to the footer totals.
    """
    seen: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        txn_id = row.values.get("txn_id", "")
        if txn_id:
            seen[txn_id].append(row.row_number)

    dupes = {tid: nums for tid, nums in seen.items() if len(nums) > 1}
    if not dupes:
        return None

    detail = "; ".join(
        f"{tid} on rows {', '.join(str(n) for n in sorted(nums))}"
        for tid, nums in sorted(dupes.items())
    )
    return Refusal(
        "duplicate_txn_id",
        f"Sync refused: worksheet {title!r} carries a duplicate Txn ID — {detail}. "
        f"Remove the extra row before syncing; sync cannot tell which is real.",
    )
