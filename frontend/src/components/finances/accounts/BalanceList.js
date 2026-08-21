import React from 'react';
import SyncChip from './SyncChip';
import { fmt$ } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';

// Flex-row list for balance-style accounts — cash and investments both render
// through here, so the two groups can't drift into different row treatments.
// Replaces the old CashList, which hardcoded the "Cash & Savings" heading and
// was rendered alongside a second, differently-filtered copy of the same
// accounts in BalancesSection.
//
// `total` is shown as a tag in the heading; pass the matching figure from the
// summary (total_cash / total_investments) rather than re-summing here, so the
// heading agrees with the Net Worth page.
export default function BalanceList({
  title,
  icon,
  accounts,
  total,
  cacheFetchedAt,
  onAdd,
  addLabel,
  onEdit,
  onDelete,
}) {
  if (!accounts.length && !onAdd) return null;

  return (
    <div className="finances-section acct-cash-card">
      <div className="acct-list-head">
        <h2 className="finances-section-title">{title}</h2>
        {(total !== null && total !== undefined) && (
          <span className="acct-list-total">{fmt$(total)}</span>
        )}
      </div>
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
                {icon}
              </div>
              <div className="acct-row-meta">
                <div className="acct-row-name">
                  {acct.name}
                  <SyncChip manual={acct.manual} cacheFetchedAt={cacheFetchedAt} />
                </div>
                <div className="acct-row-inst">{acct.institution}</div>
                {acct.manual && acct.linked_txn_count > 0 && (
                  <div
                    className="ov-balance-linked-meta"
                    title="Live balance = starting balance + signed delta of linked transactions"
                  >
                    from {acct.linked_txn_count} linked
                    {' '}txn{acct.linked_txn_count === 1 ? '' : 's'}
                  </div>
                )}
              </div>
              <div className="acct-cash-balance">
                <div className="acct-balance-owed acct-balance-pos">{fmt$(avail)}</div>
                {showLedger && (
                  <div className="acct-balance-sub">{fmt$(ledger)} ledger</div>
                )}
              </div>
              {acct.manual && (onEdit || onDelete) && (
                <div className="acct-row-actions">
                  {onEdit && (
                    <button
                      type="button"
                      className="ov-icon-btn"
                      onClick={() => onEdit(acct)}
                      aria-label={`Edit balance for ${acct.name}`}
                      title="Edit balance"
                    >✎</button>
                  )}
                  {onDelete && (
                    <button
                      type="button"
                      className="ov-icon-btn ov-icon-btn--danger"
                      onClick={() => onDelete(acct)}
                      aria-label={`Remove ${acct.name}`}
                      title="Remove account"
                    >✕</button>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {onAdd && (
          <button type="button" className="acct-add-row" onClick={onAdd}>
            <span aria-hidden="true">+</span>
            <span>{addLabel}</span>
          </button>
        )}
      </div>
    </div>
  );
}
