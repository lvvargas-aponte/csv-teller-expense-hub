import React, { useState } from 'react';
import InlineField from './InlineField';
import { fmt$, formatRelativeTime } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';

function toNum(v) {
  if (v === '' || v === null || v === undefined) return null;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

// Two-tier credit/loan row. Clicking the row expands an inline drawer holding
// the fields the bank doesn't sync (limit, APR, minimum, statement/due day).
//
// The account name never truncates — long names wrap to a second line. Meta
// values that are missing are omitted entirely rather than rendered as a dash,
// which is what made the old eight-column table read as mostly empty.
//
// A manual account additionally offers "Edit balance" and "Remove" — a
// synced balance comes from the bank and must never be hand-edited, so those
// controls exist only when `row.manual` is true AND the parent supplied the
// corresponding handler. The row also passes `row.manual` on every call, and
// AccountsTab's handlers bail if it's false — a second, independent check
// that doesn't rely on this component alone getting the gating right.
export default function AccountListRow({
  row,
  needsReconnect = false,
  cacheFetchedAt,
  onUpdate,
  onEditBalance,
  onDelete,
}) {
  const [open, setOpen] = useState(false);
  const [editingBalance, setEditingBalance] = useState(false);
  const [owed, setOwed] = useState('');
  const [available, setAvailable] = useState('');
  const palette = chipColorFor(row.institution);
  const meta = buildMeta(row, needsReconnect, cacheFetchedAt);

  const canEditBalance = !!(row.manual && onEditBalance);
  const canDelete = !!(row.manual && onDelete);
  const hasActions = canEditBalance || canDelete;

  const openBalanceEditor = (e) => {
    e.stopPropagation();
    setOwed(row.owed === null || row.owed === undefined ? '' : String(row.owed));
    setAvailable(row.available === null || row.available === undefined ? '' : String(row.available));
    setEditingBalance(true);
    setOpen(false);
  };

  const saveBalance = (e) => {
    e.stopPropagation();
    // The row displays owed/available, but updateAccountBalance's contract is
    // { available, ledger } — owed is the credit account's ledger.
    onEditBalance?.(row.id, row.manual, { available: toNum(available), ledger: toNum(owed) });
    setEditingBalance(false);
  };

  return (
    <div className="acct-row-group" role="group" aria-label={row.name}>
      <div
        className={`acct-row${hasActions ? ' acct-row--actions' : ''}`}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen((o) => !o);
          }
        }}
      >
        <div
          className="acct-row-avatar"
          style={{ background: palette.bg, color: palette.color }}
          aria-hidden="true"
        >
          💳
        </div>

        <div className="acct-row-body">
          <div className="acct-row-title">{row.name}</div>
          <MetaLine items={meta} />
        </div>

        <div className="acct-row-amount">
          <div className={`acct-row-balance${row.owed === 0 ? ' is-zero' : ''}`}>
            {fmt$(row.owed)}
          </div>
          <div className="acct-row-subamount">{fmt$(row.available)} available</div>
        </div>

        {hasActions && (
          <div className="acct-row-actions">
            {canEditBalance && (
              <button
                type="button"
                className="ov-icon-btn"
                onClick={openBalanceEditor}
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
                onClick={(e) => { e.stopPropagation(); onDelete(row.id, row.manual, row.name); }}
                aria-label="Remove"
                title="Remove"
              >
                <span aria-hidden="true">✕</span>
              </button>
            )}
          </div>
        )}

        <div className={`acct-row-chevron${open ? ' is-open' : ''}`} aria-hidden="true">›</div>
      </div>

      {editingBalance && (
        <div className="acct-drawer" role="presentation" onClick={(e) => e.stopPropagation()}>
          <DrawerField label="Balance owed">
            <input
              className="ifield ifield--boxed"
              type="number"
              step="0.01"
              aria-label={`Balance owed, for ${row.name}`}
              value={owed}
              onChange={(e) => setOwed(e.target.value)}
            />
          </DrawerField>
          <DrawerField label="Available credit">
            <input
              className="ifield ifield--boxed"
              type="number"
              step="0.01"
              aria-label={`Available, for ${row.name}`}
              value={available}
              onChange={(e) => setAvailable(e.target.value)}
            />
          </DrawerField>
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

      {open && (
        <div className="acct-drawer" role="presentation" onClick={(e) => e.stopPropagation()}>
          <DrawerField label="Credit limit">
            <InlineField
              value={row.limit}
              onChange={(v) => onUpdate('credit_limit', v)}
              type="number"
              prefix="$"
              placeholder="$ limit"
              className="ifield--boxed"
              step="0.01"
              min="0"
            />
          </DrawerField>
          <DrawerField label="APR">
            <InlineField
              value={row.apr}
              onChange={(v) => onUpdate('apr', v)}
              type="number"
              suffix="%"
              placeholder="%"
              className="ifield--boxed"
              step="0.01"
              min="0"
            />
          </DrawerField>
          <DrawerField label="Min payment">
            <InlineField
              value={row.minPayment}
              onChange={(v) => onUpdate('minimum_payment', v)}
              type="number"
              prefix="$"
              placeholder="$ min"
              className="ifield--boxed"
              step="0.01"
              min="0"
            />
          </DrawerField>
          <DrawerField label="Statement day">
            <InlineField
              value={row.statementDay}
              onChange={(v) => onUpdate('statement_day', v)}
              type="number"
              placeholder="day of month"
              className="ifield--boxed"
              step="1"
              min="1"
              max="31"
            />
          </DrawerField>
          <DrawerField label="Due day">
            <InlineField
              value={row.dueDay}
              onChange={(v) => onUpdate('due_day', v)}
              type="number"
              placeholder="day of month"
              className="ifield--boxed"
              step="1"
              min="1"
              max="31"
            />
          </DrawerField>
          <DrawerField label="Opened on">
            {/* Length of credit history is the one score factor no bank feed
                carries — SimpleFIN reports balances, not an open date. */}
            <InlineField
              value={row.openedOn}
              onChange={(v) => onUpdate('opened_on', v)}
              type="text"
              placeholder="YYYY-MM-DD"
              className="ifield--boxed"
            />
          </DrawerField>
          {row.manual && (
            <div className="acct-drawer-note">
              Manual account — these values aren’t synced from {row.institution}.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DrawerField({ label, children }) {
  return (
    // eslint-disable-next-line jsx-a11y/label-has-associated-control
    <label className="acct-drawer-field">
      <span className="acct-drawer-label">{label}</span>
      {children}
    </label>
  );
}

export function MetaLine({ items }) {
  if (!items.length) return null;
  return (
    <div className="acct-row-meta">
      {items.map((m, i) => (
        <React.Fragment key={m.text}>
          {i > 0 && <span className="acct-meta-sep" aria-hidden="true">·</span>}
          <span className={m.warn ? 'acct-meta-warn' : undefined}>{m.text}</span>
        </React.Fragment>
      ))}
    </div>
  );
}

function buildMeta(row, needsReconnect, cacheFetchedAt) {
  const items = [];
  const push = (text, warn = false) => { if (text) items.push({ text, warn }); };

  push(row.institution);
  if (row.manual) push('manual');
  else if (needsReconnect) push('needs reconnect', true);

  if (row.utilPct !== null) push(`${Math.round(row.utilPct)}% used`);
  if (row.apr) push(`${row.apr}% APR`);

  if (row.dueDay) {
    const d = row.dueInDays;
    const soon = d !== null && d !== undefined && d <= 7;
    push(soon ? `due day ${row.dueDay} · ${d === 0 ? 'today' : `${d}d`}` : `due day ${row.dueDay}`, soon);
  }
  if (row.minPayment) push(`min ${fmt$(row.minPayment)}`);
  if (!row.manual && cacheFetchedAt) push(`synced ${formatRelativeTime(cacheFetchedAt)}`);

  return items;
}
