import React, { useMemo } from 'react';
import { fmt$ } from '../../../utils/formatting';
import { daysUntilNextDue } from './dueDate';

// Right-rail summary for the Accounts page: what's on this page, totalled.
//
// This card used to headline a "Net worth" of cash − owed, computed locally.
// That figure counted neither investments nor property equity while still
// subtracting mortgages (which arrive from the bank as `credit` accounts), so a
// household with real equity read as deeply negative — and it disagreed with
// the summary's own net_worth rendered further down the same page. Net worth is
// now one number, on its own page, from summary.net_worth. What's left here is
// strictly the account roster's own totals.
export default function AccountsSummaryCard({
  creditAccounts,
  cashAccounts,
  investmentAccounts = [],
  totals = {},
  detailsMap,
  onViewNetWorth,
}) {
  const stats = useMemo(() => {
    const sumAvailable = (list) =>
      list.reduce((s, a) => s + (parseFloat(a.available) || 0), 0);

    // Prefer the server's totals so this card agrees with the Net Worth page;
    // fall back to summing the rows when a caller passes accounts only.
    const totalCash = totals.cash ?? sumAvailable(cashAccounts);
    const totalInvestments = totals.investments ?? sumAvailable(investmentAccounts);
    const totalOwed = totals.credit
      ?? creditAccounts.reduce((s, a) => s + (parseFloat(a.ledger) || 0), 0);
    const totalAvail = sumAvailable(creditAccounts);

    // "Next payment" = card with the soonest due date that has a positive
    // minimum payment. If multiple are tied, pick the largest min payment.
    let nextDue = null;
    creditAccounts.forEach((a) => {
      const d = detailsMap[a.id] || {};
      const min = parseFloat(d.minimum_payment) || 0;
      if (!d.due_day || min <= 0) return;
      const days = daysUntilNextDue(d.due_day);
      if ((days === null || days === undefined)) return;
      if (
        !nextDue ||
        days < nextDue.days ||
        (days === nextDue.days && min > nextDue.min)
      ) {
        nextDue = { days, min, name: a.name, dueDay: d.due_day };
      }
    });

    return { totalCash, totalInvestments, totalOwed, totalAvail, nextDue };
  }, [creditAccounts, cashAccounts, investmentAccounts, totals, detailsMap]);

  return (
    <div className="acct-rail-card">
      <h3 className="acct-rail-title">On this page</h3>

      <div className="acct-rail-row">
        <span className="acct-rail-label">Cash &amp; savings</span>
        <span className="acct-rail-value is-pos">{fmt$(stats.totalCash)}</span>
      </div>

      {stats.totalInvestments > 0 && (
        <div className="acct-rail-row">
          <span className="acct-rail-label">Investments</span>
          <span className="acct-rail-value">{fmt$(stats.totalInvestments)}</span>
        </div>
      )}

      <div className="acct-rail-row">
        <span className="acct-rail-label">Owed</span>
        <span className={`acct-rail-value ${stats.totalOwed > 0 ? 'is-neg' : ''}`}>
          {fmt$(stats.totalOwed)}
        </span>
      </div>

      <div className="acct-rail-row">
        <span className="acct-rail-label">Avail. credit</span>
        <span className="acct-rail-value">{fmt$(stats.totalAvail)}</span>
      </div>

      {stats.nextDue && (
        <div className="acct-rail-row">
          <span className="acct-rail-label">Next payment</span>
          <span className="acct-rail-value is-amber">
            {fmt$(stats.nextDue.min)}
            <div className="acct-rail-sub">
              {stats.nextDue.name} · day {stats.nextDue.dueDay}
              {stats.nextDue.days === 0
                ? ' · today'
                : ` · in ${stats.nextDue.days}d`}
            </div>
          </span>
        </div>
      )}

      {onViewNetWorth && (
        <button type="button" className="acct-rail-link" onClick={onViewNetWorth}>
          Net worth — including property equity →
        </button>
      )}
    </div>
  );
}
