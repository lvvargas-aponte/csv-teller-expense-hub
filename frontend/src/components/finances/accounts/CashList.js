import React from 'react';
import SyncChip from './SyncChip';
import { fmt$ } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';

// Read-only flex-row list for depository accounts. Account creation/edit lives
// on the Overview tab in BalancesSection — this view is just the at-a-glance
// list that lives next to the credit-cards table.
export default function CashList({ accounts, cacheFetchedAt, onAdd }) {
  if (!accounts.length && !onAdd) return null;

  return (
    <div className="finances-section acct-cash-card">
      <h2 className="finances-section-title">Cash &amp; Savings</h2>
      <div className="acct-cash-list">
        {accounts.map((acct) => {
          const palette = chipColorFor(acct.institution);
          const avail = parseFloat(acct.available) || 0;
          const ledger = parseFloat(acct.ledger) || 0;
          const showLedger = Math.abs(avail - ledger) > 0.005;
          return (
            <div key={acct.id} className="acct-cash-row">
              <div
                className="acct-row-icon"
                style={{ background: palette.bg, color: palette.color }}
              >
                🏦
              </div>
              <div className="acct-row-meta">
                <div className="acct-row-name">
                  {acct.name}
                  <SyncChip manual={acct.manual} cacheFetchedAt={cacheFetchedAt} />
                </div>
                <div className="acct-row-inst">{acct.institution}</div>
              </div>
              <div className="acct-cash-balance">
                <div className="acct-balance-owed acct-balance-pos">{fmt$(avail)}</div>
                {showLedger && (
                  <div className="acct-balance-sub">{fmt$(ledger)} ledger</div>
                )}
              </div>
            </div>
          );
        })}
        {onAdd && (
          <button type="button" className="acct-add-row" onClick={onAdd}>
            <span aria-hidden="true">+</span>
            <span>Add bank account or savings</span>
          </button>
        )}
      </div>
    </div>
  );
}
