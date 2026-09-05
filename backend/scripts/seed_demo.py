"""Populate a demo database with fictitious data for the README screenshots.

Every figure here is invented. The script refuses to run against any database
whose name does not end in ``_demo``, so it can never overwrite real data --
see :func:`_assert_demo_db`.

    docker compose -f docker-compose.demo.yaml -p finfree-demo
        run --rm backend python -m scripts.seed_demo
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

import categories_service
import categorization_service
import config
import state
from csv_parser import BankType, Transaction
from db.accounts_repo import get_repo
from db.base import sync_engine

RNG = random.Random(20260905)

# The demo household. Deliberately not anyone's real name.
PERSON_1 = "Alex"
PERSON_2 = "Sam"

MONTHS_OF_HISTORY = 5


def _assert_demo_db() -> None:
    url = config.DATABASE_URL or ""
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not db_name.endswith("_demo"):
        sys.exit(
            f"refusing to seed: DATABASE_URL points at {db_name!r}, which is not "
            "a demo database. Run this only against the docker-compose.demo.yaml stack."
        )


def _wipe() -> None:
    """Clear anything a previous run left, so seeding is idempotent."""
    with sync_engine.begin() as conn:
        conn.execute(text("DELETE FROM json_stores"))
        conn.execute(
            text(
                "TRUNCATE conversations, conversation_turns, balance_snapshots, "
                "holdings, account_details, accounts, categories, category_rules, "
                "budgets, goals, user_facts, user_profile RESTART IDENTITY CASCADE"
            )
        )
    categories_service._invalidate()


def _iso(d: date) -> str:
    return d.isoformat()


def _month_start(offset: int) -> date:
    """First day of the month ``offset`` months before the current one."""
    d = date.today().replace(day=1)
    for _ in range(offset):
        d = (d - timedelta(days=1)).replace(day=1)
    return d


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

ACCOUNTS = [
    # (key, institution, name, type, subtype, available, ledger)
    ("checking",  "Lakeside Bank",   "Everyday Checking",    "depository", "checking",     4812.66,  4812.66),
    ("savings",   "Lakeside Bank",   "Emergency Savings",    "depository", "savings",     11250.00, 11250.00),
    ("rewards",   "Horizon Card",    "Horizon Rewards Card", "credit",     "credit_card",     0.00,  1842.19),
    ("travel",    "Summit Bank",     "Summit Travel Card",   "credit",     "credit_card",     0.00,   623.40),
    ("auto",      "Summit Bank",     "Auto Loan",            "credit",     "loan",            0.00, 12480.00),
    ("brokerage", "Meridian Invest", "Brokerage",            "investment", "brokerage",   18430.12, 18430.12),
]

DETAILS = {
    "rewards": {"apr": 21.99, "credit_limit": 9000.0, "minimum_payment": 55.0,
                "statement_day": 18, "due_day": 12, "opened_on": date(2019, 3, 14)},
    "travel":  {"apr": 24.49, "credit_limit": 6000.0, "minimum_payment": 35.0,
                "statement_day": 6, "due_day": 1, "opened_on": date(2022, 8, 2)},
    "auto":    {"apr": 6.40, "credit_limit": None, "minimum_payment": 428.0,
                "statement_day": 1, "due_day": 20, "opened_on": date(2024, 5, 9)},
}

# Where each account sat at the start of each month across the history window,
# so the net-worth and balance trends have shape rather than a flat line.
TRAJECTORY = {
    "checking":  [3980.12, 4155.40, 3872.90, 4410.08, 4602.31, 4812.66],
    "savings":   [8750.00, 9250.00, 9750.00, 10250.00, 10750.00, 11250.00],
    "rewards":   [2610.44, 2418.77, 2205.03, 2094.88, 1961.20, 1842.19],
    "travel":    [1180.22, 984.10, 852.66, 741.09, 688.75, 623.40],
    "auto":      [14620.00, 14192.00, 13764.00, 13336.00, 12908.00, 12480.00],
    "brokerage": [15120.55, 15880.31, 16402.77, 17110.62, 17904.40, 18430.12],
}


def _seed_accounts() -> dict:
    repo = get_repo()
    ids: dict = {}
    for key, institution, name, type_, subtype, available, ledger in ACCOUNTS:
        acct_id = f"demo_{key}"
        ids[key] = acct_id
        state._manual_accounts[acct_id] = {
            "id": acct_id, "institution": institution, "name": name,
            "type": type_, "subtype": subtype,
            "available": available, "ledger": ledger,
        }
        repo.upsert_manual_account(
            account_id=acct_id, institution=institution, name=name,
            type_=type_, subtype=subtype,
        )
        for offset, amount in enumerate(TRAJECTORY[key]):
            captured = _month_start(MONTHS_OF_HISTORY - offset)
            is_debt = type_ == "credit"
            repo.insert_balance_snapshot(
                account_id=acct_id,
                source="manual",
                available=None if is_debt else amount,
                ledger=amount,
                raw={"demo": True},
                captured_at=datetime.combine(
                    captured, datetime.min.time()
                ).replace(tzinfo=timezone.utc).isoformat(),
            )

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    for key, detail in DETAILS.items():
        state.account_details[ids[key]] = {
            "account_id": ids[key],
            **{k: (_iso(v) if isinstance(v, date) else v) for k, v in detail.items()},
            "created": now,
            "updated": now,
        }
    return ids


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

# (merchant, category, amount, day-of-month, account) -- the fixed spine of
# every month, which is also what lets the commitments page detect anything.
RECURRING = [
    ("LAKESIDE POWER & LIGHT", "Utilities",      118.42,  3, "checking"),
    ("CELLWAVE WIRELESS",      "Utilities",       85.00, 14, "rewards"),
    ("STREAMLY",               "Subscriptions",   17.99,  4, "rewards"),
    ("TUNEBOX PREMIUM",        "Subscriptions",   11.99, 19, "rewards"),
    ("IRONWORKS GYM",          "Health",          39.00,  6, "rewards"),
    ("BRIGHTSHIELD AUTO INS",  "Insurance",      128.44, 22, "checking"),
    ("SUMMIT BANK AUTO LOAN",  "Other",          428.00, 20, "checking"),
]

# (merchant, category, low, high, times-per-month, account)
VARIABLE = [
    ("GREENLEAF MARKET",   "Groceries",     42.00, 138.00, 4, "rewards"),
    ("CORNER GROCER",      "Groceries",     18.00,  62.00, 2, "rewards"),
    ("BLUE BOTTLE COFFEE", "Dining",         4.50,  14.00, 5, "rewards"),
    ("NOODLE HOUSE",       "Dining",        22.00,  58.00, 2, "travel"),
    ("TRATTORIA VERDE",    "Dining",        38.00,  96.00, 1, "travel"),
    ("PETRO EXPRESS",      "Gas",           32.00,  61.00, 3, "rewards"),
    ("CITY TRANSIT",       "Transport",      2.75,   2.75, 6, "rewards"),
    ("HARBOR HARDWARE",    "Shopping",      12.00, 145.00, 1, "rewards"),
    ("MERIDIAN BOOKS",     "Shopping",       9.00,  48.00, 1, "rewards"),
    ("WESTGATE PHARMACY",  "Health",        11.00,  74.00, 1, "rewards"),
    ("ORPHEUM CINEMA",     "Entertainment", 16.00,  42.00, 1, "travel"),
]

# Split down the middle with the other person, one of each per month.
SHARED = [
    ("GREENLEAF MARKET",       "Groceries",   96.40,  2, "Weekly shop"),
    ("HEARTHSTONE PROPERTIES", "Rent",      1850.00,  1, "Rent"),
    ("NORTHWIND FIBER",        "Utilities",   79.99,  4, "Internet"),
]

INCOME = [("ORBIT LABS PAYROLL", 3240.55, 15), ("ORBIT LABS PAYROLL", 3240.55, 28)]

# Cards get paid down every month; without these the demo's utilization
# climbs all the way through the history window.
CARD_PAYMENTS = [
    ("PAYMENT - THANK YOU", 940.00, 12, "rewards"),
    ("PAYMENT - THANK YOU", 175.00, 2, "travel"),
]

ACCOUNT_TYPE = {
    "checking": "checking", "savings": "savings", "rewards": "credit_card",
    "travel": "credit_card", "auto": "loan", "brokerage": "investment",
}
INSTITUTION = {row[0]: row[1] for row in ACCOUNTS}


def _txn(day: date, desc: str, amount: float, category: str, acct_key: str,
         ids: dict, *, credit: bool = False, **extra) -> Transaction:
    return Transaction(
        date=_iso(day),
        description=desc,
        amount=round(amount, 2),
        source=BankType.SIMPLEFIN,
        post_date=_iso(day),
        category=category,
        account_id=ids[acct_key],
        institution=INSTITUTION[acct_key],
        transaction_type="credit" if credit else "debit",
        account_type=ACCOUNT_TYPE[acct_key],
        reviewed=True,
        **extra,
    )


def _level_current_month(rows: list, ids: dict) -> list:
    """Leave this month's spend roughly where the month is, and return it.

    Budgets are read for the current month, so on the 3rd of the month the
    page is either empty or -- if one grocery run has landed -- pacing to
    triple its cap. Neither is what the app normally looks like. Each
    budgeted category is levelled to the share of the month that has
    elapsed: discretionary rows are dropped while it is over, and one more
    purchase is added while it is under.
    """
    today = date.today()
    start = _month_start(0)
    elapsed = (today - start).days + 1
    progress = elapsed / 30
    merchants = {c: (m, a) for m, c, _lo, _hi, _n, a in VARIABLE}
    discretionary = {m for m, *_ in VARIABLE}

    def this_month(txn) -> bool:
        return txn.date >= _iso(start) and txn.transaction_type == "debit"

    spent: dict = {}
    for txn in rows:
        if this_month(txn):
            spent[txn.category] = spent.get(txn.category, 0.0) + txn.amount

    kept = list(rows)
    extra = []
    for category, limit in BUDGETS.items():
        if category not in merchants:
            continue
        target = limit * progress * RNG.uniform(0.65, 0.95)

        droppable = sorted(
            (t for t in kept
             if this_month(t) and t.category == category
             and t.description in discretionary and not t.is_shared),
            key=lambda t: t.amount,
            reverse=True,
        )
        while spent.get(category, 0.0) > target and droppable:
            victim = droppable.pop(0)
            kept.remove(victim)
            spent[category] -= victim.amount

        deficit = target - spent.get(category, 0.0)
        if deficit < 5:
            continue
        merchant, acct = merchants[category]
        when = start + timedelta(days=RNG.randint(0, max(0, elapsed - 1)))
        extra.append(_txn(when, merchant, deficit, category, acct, ids))
    return kept + extra


def _seed_transactions(ids: dict) -> int:
    today = date.today()
    rows = []

    for offset in range(MONTHS_OF_HISTORY, -1, -1):
        start = _month_start(offset)

        def day(n: int, _start=start):
            d = _start.replace(day=min(n, 28))
            return None if d > today else d

        for desc, category, amount, dom, acct in RECURRING:
            d = day(dom)
            if d:
                rows.append(_txn(d, desc, amount, category, acct, ids))

        for desc, amount, dom, acct in CARD_PAYMENTS:
            d = day(dom)
            if d:
                rows.append(_txn(
                    d, desc, amount, "Payments and Credits", acct, ids, credit=True,
                ))

        for desc, amount, dom in INCOME:
            d = day(dom)
            if d:
                rows.append(_txn(d, desc, amount, "Income", "checking", ids, credit=True))

        # The current month is only part-spent, so its variable spending is
        # scaled to the days elapsed — otherwise a full month of groceries
        # lands in the first week and every budget reads as blown.
        span = 28 if offset else min(28, today.day)
        for desc, category, low, high, per_month, acct in VARIABLE:
            count = per_month if offset else round(per_month * span / 28)
            for _ in range(count):
                d = day(RNG.randint(1, span))
                if d:
                    rows.append(_txn(d, desc, RNG.uniform(low, high), category, acct, ids))

        for desc, category, amount, dom, note in SHARED:
            d = day(dom)
            if d:
                rows.append(_txn(
                    d, desc, amount, category, "checking", ids,
                    is_shared=True, who=PERSON_1, what=note,
                    person_2_owes=round(amount / 2, 2), notes=note,
                ))

    rows = _level_current_month(rows, ids)
    rows.sort(key=lambda t: t.date)
    # A handful left unreviewed so the "needs review" affordances aren't empty.
    for txn in rows[-6:]:
        txn.reviewed = False

    for txn in rows:
        state.stored_transactions[txn.transaction_id] = (
            categorization_service.stamp_ingest(txn.to_dict())
        )
    categories_service.ensure_seeded()
    categories_service.ensure_many(t.category for t in rows)
    return len(rows)


# ---------------------------------------------------------------------------
# Plan: budgets, goals, rules, profile
# ---------------------------------------------------------------------------

BUDGETS = {
    "Groceries": 650, "Dining": 320, "Gas": 180, "Shopping": 220,
    "Entertainment": 120, "Health": 150,
}

GOALS = [
    ("Emergency fund",     15000.0, 11250.0, "emergency", "savings", None),
    ("Japan, next spring",  6000.0,  2150.0, "savings",   None, date(2027, 4, 1)),
    ("Replace the laptop",  2400.0,   900.0, "savings",   None, date(2026, 12, 15)),
]

RULES = [
    ("contains", "GREENLEAF", "Groceries"),
    ("contains", "BLUE BOTTLE", "Dining"),
    ("contains", "CITY TRANSIT", "Transport"),
    ("contains", "PETRO EXPRESS", "Gas"),
]


def _seed_plan(ids: dict) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    for category, limit in BUDGETS.items():
        state.budgets[category] = {
            "category": category, "monthly_limit": float(limit),
            "notes": "", "created": now, "updated": now,
        }

    for i, (name, target, current, kind, linked, target_date) in enumerate(GOALS):
        goal_id = f"demo_goal_{i}"
        state.goals[goal_id] = {
            "id": goal_id, "name": name,
            "target_amount": target, "current_balance": current,
            "target_date": _iso(target_date) if target_date else None,
            "linked_account_id": ids[linked] if linked else None,
            "kind": kind, "notes": "", "created": now, "updated": now,
        }

    with sync_engine.begin() as conn:
        for position, (kind, pattern, category) in enumerate(RULES):
            conn.execute(
                text(
                    "INSERT INTO category_rules (kind, pattern, category, position, enabled) "
                    "VALUES (:kind, :pattern, :category, :position, true)"
                ),
                {"kind": kind, "pattern": pattern, "category": category,
                 "position": position},
            )
        conn.execute(
            text(
                "INSERT INTO user_profile (id, risk_tolerance, time_horizon_years, "
                "dependents, debt_strategy, monthly_income, emergency_fund_months, "
                "birth_year, target_retirement_age, annual_retirement_spend, "
                "expected_return_pct) VALUES ('household', 'balanced', 25, 0, "
                "'avalanche', 6481.10, 6, 1992, 62, 58000, 6.5)"
            )
        )


def main() -> None:
    _assert_demo_db()
    _wipe()
    ids = _seed_accounts()
    count = _seed_transactions(ids)
    _seed_plan(ids)
    print(
        f"seeded {len(ids)} accounts, {count} transactions, "
        f"{len(BUDGETS)} budgets, {len(GOALS)} goals"
    )


if __name__ == "__main__":
    main()
