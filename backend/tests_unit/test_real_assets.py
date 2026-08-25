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
