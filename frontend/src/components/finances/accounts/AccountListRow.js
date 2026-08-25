import React, { useState } from 'react';
import InlineField from './InlineField';
import { fmt$, formatRelativeTime } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';

// Two-tier credit/loan row. Clicking the row expands an inline drawer holding
// the fields the bank doesn't sync (limit, APR, minimum, statement/due day).
//
// The account name never truncates — long names wrap to a second line. Meta
// values that are missing are omitted entirely rather than rendered as a dash,
// which is what made the old eight-column table read as mostly empty.
export default function AccountListRow({
  row,
  needsReconnect = false,
  cacheFetchedAt,
  onUpdate,
}) {
  const [open, setOpen] = useState(false);
  const palette = chipColorFor(row.institution);
  const meta = buildMeta(row, needsReconnect, cacheFetchedAt);

  return (
    <>
      <div
        className="acct-row"
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

        <div className={`acct-row-chevron${open ? ' is-open' : ''}`} aria-hidden="true">›</div>
      </div>

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
    </>
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
