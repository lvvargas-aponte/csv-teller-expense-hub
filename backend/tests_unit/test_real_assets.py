"""Real assets — homes and vehicles in net worth.

A mortgage is filed as ``type='credit'`` and counted in full, so before this
bucket existed the house behind it had nowhere to live and net worth was
structurally wrong for any homeowner. These tests pin the two halves that
matter: the value reaches net worth, and it does *not* reach spendable cash
(which would inflate the emergency-fund runway by six figures).
"""
import uuid

import pytest

import state
from balances_service import build_summary


def _add_manual_account(**fields):
    acct_id = f"manual_{uuid.uuid4().hex[:12]}"
    state._manual_accounts[acct_id] = {
        "id": acct_id,
        "institution": fields.pop("institution", ""),
        "name": fields.pop("name", "Account"),
        "type": fields.pop("type", "depository"),
        "subtype": fields.pop("subtype", ""),
        "available": float(fields.pop("available", 0.0)),
        "ledger": float(fields.pop("ledger", 0.0)),
        **fields,
    }
    return acct_id


def _find(accounts, account_id):
    return next(a for a in accounts if a.id == account_id)


@pytest.mark.asyncio
async def test_real_asset_raises_net_worth_but_not_cash():
    _add_manual_account(name="House", type="asset", subtype="home", available=450000.0)

    summary = await build_summary()

    assert summary.total_real_assets == 450000.0
    assert summary.total_cash == 0.0
    assert summary.net_worth == 450000.0


@pytest.mark.asyncio
async def test_transactions_do_not_revalue_a_real_asset():
    """A car payment is not a change in the car's worth."""
    car = _add_manual_account(name="Car", type="asset", subtype="vehicle", available=22000.0)
    state.stored_transactions["t1"] = {
        "id": "t1",
        "account_id": car,
        "amount": 400.0,
        "date": "2026-08-01",
        "description": "Car payment",
    }

    summary = await build_summary()
    row = _find(summary.accounts, car)

    assert row.available == 22000.0
    assert row.txn_delta == 0.0
    assert row.linked_txn_count == 0
    assert summary.total_real_assets == 22000.0


def _set_details(account_id, **fields):
    state.account_details[account_id] = {
        "account_id": account_id,
        "created": "2026-08-01T00:00:00",
        "updated": "2026-08-01T00:00:00",
        **fields,
    }


@pytest.mark.asyncio
async def test_asset_reports_equity_net_of_its_loan():
    loan = _add_manual_account(name="Mortgage", type="credit", subtype="loan", ledger=310000.0)
    home = _add_manual_account(name="House", type="asset", subtype="home", available=450000.0)
    _set_details(home, secured_by_account_id=loan)

    summary = await build_summary()
    row = _find(summary.accounts, home)

    assert row.secured_debt == 310000.0
    assert row.equity == 140000.0
    # The loan is still counted once, in total_credit_debt — not twice.
    assert summary.total_credit_debt == 310000.0
    assert summary.total_real_assets == 450000.0
    assert summary.net_worth == 140000.0


@pytest.mark.asyncio
async def test_an_unlinked_asset_reports_no_equity():
    """No link means no claim about equity — not "equity equals value"."""
    home = _add_manual_account(name="House", type="asset", subtype="home", available=450000.0)

    row = _find((await build_summary()).accounts, home)

    assert row.secured_debt is None
    assert row.equity is None


@pytest.mark.asyncio
async def test_a_stale_link_reports_null_equity_not_full_value():
    """The loan was disconnected or deleted. Showing the whole house as equity
    is the dangerous failure; saying "unknown" is the honest one."""
    home = _add_manual_account(name="House", type="asset", subtype="home", available=450000.0)
    _set_details(home, secured_by_account_id="manual_gone_forever")

    row = _find((await build_summary()).accounts, home)

    assert row.secured_debt is None
    assert row.equity is None


@pytest.mark.asyncio
async def test_equity_is_presentational_and_never_lands_on_a_non_asset_row():
    loan = _add_manual_account(name="Mortgage", type="credit", subtype="loan", ledger=310000.0)
    home = _add_manual_account(name="House", type="asset", subtype="home", available=450000.0)
    _set_details(home, secured_by_account_id=loan)

    loan_row = _find((await build_summary()).accounts, loan)

    assert loan_row.secured_debt is None
    assert loan_row.equity is None


@pytest.mark.asyncio
async def test_runway_reports_the_real_assets_it_leaves_out():
    """Illiquid value inflates net worth without improving resilience. The
    runway ignores it on purpose, so it has to say so rather than leaving the
    two numbers looking inconsistent."""
    import health_service

    _add_manual_account(name="Checking", type="depository", available=6000.0)
    _add_manual_account(name="House", type="asset", subtype="home", available=450000.0)

    fund = (await health_service.compute_ratios())["emergency_fund"]

    assert fund["cash"] == 6000.0
    assert fund["excluded_real_assets"] == 450000.0


def test_the_trend_signal_says_a_revaluation_can_move_it():
    import health_service

    trend = {"available": True, "delta_90d": 5000.0, "current_net_worth": 500000.0}

    assert "revalu" in health_service._trend_signal(trend, 450000.0)["detail"]
    # No property, no caveat — the sentence would only be noise.
    assert "revalu" not in health_service._trend_signal(trend, 0.0)["detail"]
