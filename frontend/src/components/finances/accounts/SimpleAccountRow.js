import React, { useState } from 'react';
import { MetaLine } from './AccountListRow';
import { fmt$, formatRelativeTime } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';
import { userMessage } from '../../../utils/errorMessage';
import Icon from '../../ui/Icon';

function toNum(v) {
  if (v === '' || v === null || v === undefined) return null;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

// Read-only row for cash, investment and credit accounts — same grid as the
// expandable credit row, but not expandable via click.
//
// `amount` / `amountClass` / `subAmount` override the figure on the right for
// account kinds whose headline number isn't "available cash": a card leads
// with what's owed, a brokerage with its position value. Left unset, the row
// behaves exactly as it did for cash accounts.
//
// A manual account additionally offers "Edit balance" and "Remove" — a
// synced balance comes from the bank and must never be hand-edited, so those
// controls exist only when `row.manual` is true AND the parent supplied the
// corresponding handler. The row also passes `row.manual` on every call, and
// AccountsTab's handlers bail if it's false — a second, independent check
// that doesn't rely on this component alone getting the gating right.
export default function SimpleAccountRow({
  row,
  glyph = '🏦',
  needsReconnect = false,
  cacheFetchedAt,
  onEditBalance,
  onDelete,
  amount,
  amountClass = 'is-positive',
  subAmount,
}) {
  const palette = chipColorFor(row.institution);
  const [editingBalance, setEditingBalance] = useState(false);
  const [available, setAvailable] = useState('');
  const [ledger, setLedger] = useState('');
  const [saveError, setSaveError] = useState(null);

  const canEditBalance = !!(row.manual && onEditBalance);
  const canDelete = !!(row.manual && onDelete);
  const hasActions = canEditBalance || canDelete;

  const openEditor = () => {
    // Seed from the starting balance, not row.available — that's the live
    // computed value (starting minus linked-txn delta), and re-saving it
    // unchanged would walk the stored balance down by the delta every time.
    const starting = row.startingBalance ?? row.available;
    setAvailable(starting === null || starting === undefined ? '' : String(starting));
    setLedger(row.ledger === null || row.ledger === undefined ? '' : String(row.ledger));
    setSaveError(null);
    setEditingBalance(true);
  };

  const saveBalance = async () => {
    setSaveError(null);
    try {
      await onEditBalance?.(row.id, row.manual, { available: toNum(available), ledger: toNum(ledger) });
      setEditingBalance(false);
    } catch (e) {
      setSaveError(userMessage(e, 'Could not save balance'));
    }
  };

  const meta = [];
  if (row.institution) meta.push({ text: row.institution });
  if (row.manual) meta.push({ text: 'manual' });
  else if (needsReconnect) meta.push({ text: 'needs reconnect', warn: true });
  if (!row.manual && cacheFetchedAt) {
    meta.push({ text: `synced ${formatRelativeTime(cacheFetchedAt)}` });
  }

  return (
    <div className="acct-row-group" role="group" aria-label={row.name}>
      <div className={`acct-row acct-row--static${hasActions ? ' acct-row--actions' : ''}`}>
        <div
          className="acct-row-avatar"
          style={{ background: palette.bg, color: palette.color }}
          aria-hidden="true"
        >
          {glyph}
        </div>
        <div className="acct-row-body">
          <div className="acct-row-title">{row.name}</div>
          <MetaLine items={meta} />
        </div>
        <div className="acct-row-amount">
          <div className={`acct-row-balance ${amountClass}`.trimEnd()}>
            {fmt$(amount === undefined ? row.available : amount)}
          </div>
          {subAmount === undefined
            ? row.showLedger && (
              <div className="acct-row-subamount">{fmt$(row.ledger)} ledger</div>
            )
            : subAmount && (
              <div className="acct-row-subamount">{subAmount}</div>
            )}
        </div>
        {hasActions && (
          <div className="acct-row-actions">
            {canEditBalance && (
              <button
                type="button"
                className="ov-icon-btn"
                onClick={openEditor}
                aria-label="Edit balance"
                title="Edit balance"
              >
                <Icon name="edit" size={16} />
              </button>
            )}
            {canDelete && (
              <button
                type="button"
                className="ov-icon-btn ov-icon-btn--danger"
                onClick={() => onDelete(row.id, row.manual, row.name)}
                aria-label="Remove"
                title="Remove"
              >
                <Icon name="close" size={16} />
              </button>
            )}
          </div>
        )}
      </div>

      {editingBalance && (
        <div className="acct-drawer">
          <label className="acct-drawer-field">
            <span className="acct-drawer-label">Available</span>
            <input
              className="ifield ifield--boxed"
              type="number"
              step="0.01"
              aria-label={`Available, for ${row.name}`}
              value={available}
              onChange={(e) => setAvailable(e.target.value)}
            />
          </label>
          {row.showLedger && (
            <label className="acct-drawer-field">
              <span className="acct-drawer-label">Ledger</span>
              <input
                className="ifield ifield--boxed"
                type="number"
                step="0.01"
                aria-label={`Ledger, for ${row.name}`}
                value={ledger}
                onChange={(e) => setLedger(e.target.value)}
              />
            </label>
          )}
          <div className="acct-drawer-note">
            {row.linkedTxnCount > 0
              ? `Computed from ${row.linkedTxnCount} linked txn${row.linkedTxnCount === 1 ? '' : 's'}. `
              : ''}
            Saving records a new balance snapshot.
          </div>
          {saveError && (
            <div className="acct-drawer-note acct-meta-warn">{saveError}</div>
          )}
          <div className="acct-drawer-note acct-drawer-actions">
            <button type="button" className="btn btn-secondary" onClick={() => setEditingBalance(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={saveBalance}>
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
