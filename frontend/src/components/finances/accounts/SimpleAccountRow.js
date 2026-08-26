import React, { useState } from 'react';
import { MetaLine } from './AccountListRow';
import { fmt$, formatRelativeTime } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';

function toNum(v) {
  if (v === '' || v === null || v === undefined) return null;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

// Read-only row for cash and investment accounts — same grid as the credit
// row, but not expandable via click (there is no un-synced metadata to edit).
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
}) {
  const palette = chipColorFor(row.institution);
  const [editingBalance, setEditingBalance] = useState(false);
  const [available, setAvailable] = useState('');
  const [ledger, setLedger] = useState('');

  const canEditBalance = !!(row.manual && onEditBalance);
  const canDelete = !!(row.manual && onDelete);
  const hasActions = canEditBalance || canDelete;

  const openEditor = () => {
    setAvailable(row.available === null || row.available === undefined ? '' : String(row.available));
    setLedger(row.ledger === null || row.ledger === undefined ? '' : String(row.ledger));
    setEditingBalance(true);
  };

  const saveBalance = () => {
    onEditBalance?.(row.id, row.manual, { available: toNum(available), ledger: toNum(ledger) });
    setEditingBalance(false);
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
          <div className="acct-row-balance is-positive">{fmt$(row.available)}</div>
          {row.showLedger && (
            <div className="acct-row-subamount">{fmt$(row.ledger)} ledger</div>
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
                <span aria-hidden="true">✎</span>
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
                <span aria-hidden="true">✕</span>
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
