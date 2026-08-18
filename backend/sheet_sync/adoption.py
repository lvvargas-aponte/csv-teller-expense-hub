"""One-time adoption of the pre-cutover-boundary worksheets (June, July 2026).

Everything here is planned before anything is written, and the plan is meant to
be *read*. Step 3 normalises blank owes cells to 50/50, and uneven splits do
occur in this data — the dry run is the only place that is catchable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from sheet_sync import contract, projection, worksheet
from sheet_sync.gateway import CellUpdate, SheetGateway, WorksheetExists

BACKUP_PREFIX = "_backup "


@dataclass(frozen=True)
class AdoptionRow:
    row_number: int
    description: str
    actions: List[str]
    txn_id: str = ""
    owner: str = ""
    owes_column: Optional[str] = None
    owes_value: str = ""
    bound_transaction_id: Optional[str] = None
    manual_only: bool = False


@dataclass(frozen=True)
class AdoptionPlan:
    period: str
    title: str
    backup_title: str
    headers: List[str] = field(default_factory=list)
    header_additions: List[str] = field(default_factory=list)
    rows: List[AdoptionRow] = field(default_factory=list)
    unresolved: List[AdoptionRow] = field(default_factory=list)


def backup_title_for(title: str) -> str:
    """A leading underscore is required, not cosmetic.

    The title parser anchors on a leading letter, so ``_backup June 2026``
    resolves to no period at all — which is what keeps sync from ever writing
    financial rows into the backup.
    """
    return f"{BACKUP_PREFIX}{title}"


def _cell(row: List[str], i: int) -> str:
    return (row[i] if i < len(row) else "").strip()


def _match_local(
    when, amount: Decimal, description: str, local_items
) -> Optional[str]:
    """Bind on date + amount + case-folded description. Deliberately strict:
    a wrong binding attaches a real transaction to someone else's money."""
    target = description.strip().casefold()
    for transaction_id, txn in local_items:
        local_date = contract.parse_date_loose(txn.get("date"))
        if local_date != when:
            continue
        try:
            local_amount = abs(Decimal(str(txn.get("amount", 0))))
        except Exception:
            continue
        if local_amount != amount:
            continue
        if (txn.get("description") or "").strip().casefold() == target:
            return transaction_id
    return None


def plan_adoption(
    gateway: SheetGateway,
    period: str,
    slot_to_user_id: Dict[int, str],
    person_1_name: str,
    person_2_name: str,
    local_items: List[Tuple[str, Dict[str, Any]]],
) -> AdoptionPlan:
    title = worksheet.find_worksheet(gateway, period)
    if title is None:
        raise worksheet.NoTemplateWorksheet(f"No worksheet for {period}")

    rows = gateway.read_rows(title)
    existing_headers = list(rows[0]) if rows else []
    full_headers = contract.build_headers(person_1_name, person_2_name)
    header_additions = [h for h in full_headers if h not in existing_headers]

    headers = existing_headers + header_additions
    index = contract.header_index_map(headers, person_1_name, person_2_name)
    owes_columns = {1: headers[index["owes_1"]], 2: headers[index["owes_2"]]}

    planned: List[AdoptionRow] = []
    unresolved: List[AdoptionRow] = []

    for offset, raw in enumerate(rows[1:], start=2):
        description = _cell(raw, index["description"])
        if not description and not _cell(raw, index["amount"]):
            continue
        if _cell(raw, index["txn_id"]):
            continue

        who = _cell(raw, index["who"])
        slot = projection.payer_slot(who, person_1_name, person_2_name)
        if slot is None:
            unresolved.append(
                AdoptionRow(
                    row_number=offset,
                    description=description,
                    actions=[
                        f"Who is {who or '(blank)'!r} — neither {person_1_name} nor "
                        f"{person_2_name}. Owner cannot be inferred; resolve by hand."
                    ],
                )
            )
            continue

        owner = slot_to_user_id[slot]
        when = contract.parse_date_loose(_cell(raw, index["date"]))
        try:
            amount = contract.parse_amount(_cell(raw, index["amount"]))
        except contract.ContractError:
            amount = None

        bound = (
            _match_local(when, amount, description, local_items)
            if when and amount is not None
            else None
        )
        manual_only = bound is None
        local_id = bound or f"manual-{period}-{offset}"

        actions = [
            f"Owner ← {who} ({owner})",
            f"Txn ID ← {contract.make_txn_id(owner, local_id)}"
            + ("" if bound else "  [synthetic, manual-only]"),
        ]

        owes_column = None
        owes_value = ""
        both_blank = not _cell(raw, index["owes_1"]) and not _cell(raw, index["owes_2"])
        if both_blank and amount is not None:
            non_payer = 2 if slot == 1 else 1
            owes_column = owes_columns[non_payer]
            owes_value = str(
                (amount / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
            actions.append(f"{owes_column} ← {owes_value}  (50/50 of {amount})")

        planned.append(
            AdoptionRow(
                row_number=offset,
                description=description,
                actions=actions,
                txn_id=contract.make_txn_id(owner, local_id),
                owner=owner,
                owes_column=owes_column,
                owes_value=owes_value,
                bound_transaction_id=bound,
                manual_only=manual_only,
            )
        )

    return AdoptionPlan(
        period=period,
        title=title,
        backup_title=backup_title_for(title),
        headers=headers,
        header_additions=header_additions,
        rows=planned,
        unresolved=unresolved,
    )


def render_plan(plan: AdoptionPlan) -> str:
    lines = [
        f"Adoption plan for {plan.period} — worksheet {plan.title!r}",
        f"  Backup copy:      {plan.backup_title!r}",
        f"  Headers to add:   {', '.join(plan.header_additions) or '(none)'}",
        f"  Rows to adopt:    {len(plan.rows)}",
        f"  Rows unresolved:  {len(plan.unresolved)}",
        "",
    ]

    for row in plan.rows:
        lines.append(f"  row {row.row_number}: {row.description}")
        lines.extend(f"      {a}" for a in row.actions)

    if plan.unresolved:
        lines.append("")
        lines.append("  UNRESOLVED — not written, resolve these by hand:")
        for row in plan.unresolved:
            lines.append(f"      row {row.row_number}: {row.description}")
            lines.extend(f"          {a}" for a in row.actions)

    split_rows = [r for r in plan.rows if r.owes_column]
    if split_rows:
        lines += [
            "",
            "  RISK: the rows marked 50/50 above had both owes cells blank and are",
            "  being normalised to an even split. If any of them was meant to be",
            "  uneven, this is the only place to catch it. Read, do not skim.",
        ]

    return "\n".join(lines)


def apply_adoption(gateway: SheetGateway, plan: AdoptionPlan) -> int:
    """Back up, add headers, then write the planned cells. Returns rows written."""
    if not plan.rows and not plan.header_additions:
        return 0

    try:
        gateway.duplicate_worksheet(plan.title, plan.backup_title)
    except WorksheetExists:
        pass

    if plan.header_additions:
        start = len(plan.headers) - len(plan.header_additions)
        gateway.write_cells(
            plan.title,
            [
                CellUpdate(row=1, col=start + i + 1, value=h)
                for i, h in enumerate(plan.header_additions)
            ],
        )

    positions = {h: i + 1 for i, h in enumerate(plan.headers)}
    updates: List[CellUpdate] = []
    for row in plan.rows:
        updates.append(CellUpdate(row.row_number, positions["Txn ID"], row.txn_id))
        updates.append(CellUpdate(row.row_number, positions["Owner"], row.owner))
        updates.append(CellUpdate(row.row_number, positions["Reviewed"], "TRUE"))
        if row.owes_column:
            updates.append(
                CellUpdate(row.row_number, positions[row.owes_column], row.owes_value)
            )

    if updates:
        gateway.write_cells(plan.title, updates)

    return len(plan.rows)
