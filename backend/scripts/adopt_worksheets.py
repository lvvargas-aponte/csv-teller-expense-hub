"""One-time adoption of the June and July 2026 worksheets.

Dry run by default. Writing requires --apply AND an explicit --i-have-a-backup,
because this touches a spreadsheet holding three years of settled money.

    python -m scripts.adopt_worksheets                       # dry run
    python -m scripts.adopt_worksheets --apply --i-have-a-backup
"""
from __future__ import annotations

import argparse
import sys

import identity_service
import state
from config import PERSON_1_NAME, PERSON_2_NAME
from db import identity_repo
from sheet_sync import adoption, service

PERIODS = ("2026-06", "2026-07")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument(
        "--i-have-a-backup",
        action="store_true",
        help="confirm you have an independent backup of the spreadsheet",
    )
    parser.add_argument("--period", action="append", help="override the periods")
    args = parser.parse_args()

    if args.apply and not args.i_have_a_backup:
        print("Refusing to write without --i-have-a-backup.", file=sys.stderr)
        return 2

    me = identity_service.ensure_identity()
    slots = {me["person_slot"]: me["user_id"]}
    for peer in identity_repo.list_peers():
        slots.setdefault(peer["person_slot"], peer["user_id"])

    gateway = service.build_gateway()
    local_items = list(state.stored_transactions.items())

    for period in (args.period or PERIODS):
        plan = adoption.plan_adoption(
            gateway, period, slots, PERSON_1_NAME, PERSON_2_NAME, local_items
        )
        print(adoption.render_plan(plan))
        print()

        if args.apply:
            written = adoption.apply_adoption(gateway, plan)
            print(f"Wrote {written} rows to {plan.title!r}.\n")
        else:
            print("Dry run — nothing written. Re-run with --apply "
                  "--i-have-a-backup once you have read the above.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
