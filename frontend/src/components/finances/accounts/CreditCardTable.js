import React from 'react';
import InlineField from './InlineField';
import SyncChip from './SyncChip';
import UtilBar, { utilColor } from './UtilBar';
import { fmt$ } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';
import { daysUntilNextDue, dueUrgencyClass } from './dueDate';

// Credit Cards & Loans table with inline-editable APR / Limit / Min / Statement
// / Due / Notes cells. Each cell calls onUpdate(accountId, fieldName, value)
// which the parent debounces into an upsert request.
//
// `total` is the owed figure from the summary (total_credit_debt) shown in the
// heading; edit/delete are offered per-row for manual accounts, folded in from
// the retired BalancesSection so this is the only place credit accounts appear.
export default function CreditCardTable({
  accounts,
  detailsMap,
  cacheFetchedAt,
  total,
  onUpdate,
  onAdd,
  onEdit,
  onDelete,
}) {
  if (!accounts.length && !onAdd) return null;

  const showActions = Boolean((onEdit || onDelete) && accounts.some((a) => a.manual));

  return (
    <div className="finances-section acct-table-card">
      <div className="acct-list-head">
        <h2 className="finances-section-title">Credit Cards &amp; Loans</h2>
        {(total !== null && total !== undefined) && (
          <span className="acct-list-total is-owed">{fmt$(total)} owed</span>
        )}
      </div>
      <div className="acct-table-wrap">
        <table className="acct-table">
          <thead>
            <tr>
              <th className="acct-th-account">Account</th>
              <th className="acct-th-num">Balance</th>
              <th className="acct-th-num hide-md">Util</th>
              <th className="acct-th-num hide-md">APR</th>
              <th className="acct-th-num hide-md">Limit</th>
              <th className="acct-th-num">Min</th>
              <th className="acct-th hide-md">Statement</th>
              <th className="acct-th">Due</th>
              {showActions && <th className="acct-th" aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {accounts.map((acct) => (
              <CardRow
                key={acct.id}
                account={acct}
                details={detailsMap[acct.id] || {}}
                cacheFetchedAt={cacheFetchedAt}
                showActions={showActions}
                onUpdate={(field, value) => onUpdate(acct.id, field, value)}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
          </tbody>
        </table>
        {onAdd && (
          <button type="button" className="acct-add-row" onClick={onAdd}>
            <span aria-hidden="true">+</span>
            <span>Add credit card or loan</span>
          </button>
        )}
      </div>
    </div>
  );
}

function CardRow({ account, details, cacheFetchedAt, showActions, onUpdate, onEdit, onDelete }) {
  const owed = parseFloat(account.ledger) || 0;
  const avail = parseFloat(account.available) || 0;
  const limit = (details.credit_limit !== null && details.credit_limit !== undefined) ? parseFloat(details.credit_limit) : null;
  const utilPct = limit && limit > 0 ? (owed / limit) * 100 : null;
  const days = daysUntilNextDue(details.due_day);
  const dueClass = dueUrgencyClass(days);
  const palette = chipColorFor(account.institution);

  return (
    <tr className="acct-row">
      <td className="acct-cell-account">
        <div
          className="acct-row-icon"
          style={{ background: palette.bg, color: palette.color }}
        >
          {account.type === 'credit' ? '💳' : '🏦'}
        </div>
        <div className="acct-row-meta">
          <div className="acct-row-name">
            {account.name}
            <SyncChip manual={account.manual} cacheFetchedAt={cacheFetchedAt} />
          </div>
          <div className="acct-row-inst">{account.institution}</div>
        </div>
      </td>

      <td className="acct-cell-num">
        <div className="acct-balance-owed">{fmt$(owed)}</div>
        <div className="acct-balance-sub">{fmt$(avail)} avail</div>
      </td>

      <td className="acct-cell-num hide-md">
        {(utilPct !== null && utilPct !== undefined) ? (
          <UtilBar pct={utilPct} />
        ) : (
          <span className="ifield-empty-static">—</span>
        )}
      </td>

      <td className="acct-cell-num hide-md">
        <InlineField
          value={details.apr}
          onChange={(v) => onUpdate('apr', v)}
          type="number"
          suffix="%"
          align="right"
          step="0.01"
          min="0"
        />
      </td>

      <td className="acct-cell-num hide-md">
        <InlineField
          value={details.credit_limit}
          onChange={(v) => onUpdate('credit_limit', v)}
          type="number"
          prefix="$"
          align="right"
          step="0.01"
          min="0"
        />
      </td>

      <td className="acct-cell-num">
        <InlineField
          value={details.minimum_payment}
          onChange={(v) => onUpdate('minimum_payment', v)}
          type="number"
          prefix="$"
          align="right"
          step="0.01"
          min="0"
        />
      </td>

      <td className="acct-cell hide-md">
        <InlineField
          value={details.statement_day}
          onChange={(v) => onUpdate('statement_day', v)}
          type="number"
          placeholder="day"
          step="1"
          min="1"
          max="31"
        />
      </td>

      <td className="acct-cell">
        <InlineField
          value={details.due_day}
          onChange={(v) => onUpdate('due_day', v)}
          type="number"
          placeholder="day"
          className={dueClass}
          step="1"
          min="1"
          max="31"
        />
        {(days !== null && days !== undefined) && days <= 7 && (
          <div
            className={`acct-due-countdown ${dueClass}`}
            style={{ color: dueClass === 'due-urgent' ? 'var(--red)' : 'var(--amber)' }}
          >
            {days === 0 ? 'Due today' : `${days}d`}
          </div>
        )}
      </td>

      {showActions && (
        <td className="acct-cell">
          {account.manual && (
            <div className="acct-row-actions">
              {onEdit && (
                <button
                  type="button"
                  className="ov-icon-btn"
                  onClick={() => onEdit(account)}
                  aria-label={`Edit balance for ${account.name}`}
                  title="Edit balance"
                >✎</button>
              )}
              {onDelete && (
                <button
                  type="button"
                  className="ov-icon-btn ov-icon-btn--danger"
                  onClick={() => onDelete(account)}
                  aria-label={`Remove ${account.name}`}
                  title="Remove account"
                >✕</button>
              )}
            </div>
          )}
        </td>
      )}
    </tr>
  );
}

// Re-export so callers can compute consistent colors for outside use.
export { utilColor };
