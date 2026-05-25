import React, { useMemo } from 'react';
import { fmt$, fmtSigned } from '../../../utils/formatting';
import { daysUntilNextDue } from './dueDate';

// Right-rail summary: net worth (cash − owed), available credit across all
// cards, and the next minimum payment due. Computed from props with useMemo.
export default function AccountsSummaryCard({ creditAccounts, cashAccounts, detailsMap }) {
  const stats = useMemo(() => {
    const totalCash  = cashAccounts.reduce((s, a) => s + (parseFloat(a.available) || 0), 0);
    const totalOwed  = creditAccounts.reduce((s, a) => s + (parseFloat(a.ledger) || 0), 0);
    const totalAvail = creditAccounts.reduce((s, a) => s + (parseFloat(a.available) || 0), 0);
    const netWorth   = totalCash - totalOwed;

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

    return { netWorth, totalAvail, nextDue };
  }, [creditAccounts, cashAccounts, detailsMap]);

  return (
    <div className="acct-rail-card">
      <h3 className="acct-rail-title">Summary</h3>
      <div className="acct-rail-row">
        <span className="acct-rail-label">Net worth</span>
        <span className={`acct-rail-value ${stats.netWorth < 0 ? 'is-neg' : 'is-pos'}`}>
          {fmtSigned(stats.netWorth)}
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
    </div>
  );
}
