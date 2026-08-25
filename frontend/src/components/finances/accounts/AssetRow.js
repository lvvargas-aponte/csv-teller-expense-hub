import React from 'react';
import { MetaLine } from './AccountListRow';
import InlineField from './InlineField';
import { fmt$ } from '../../../utils/formatting';

const GLYPHS = { home: '🏠', vehicle: '🚗' };

// Months after which a typed valuation is worth revisiting. Nothing in this
// app estimates what a house or a car is worth — an automatic appreciation
// curve would move net worth by six figures on a guess — so the only honest
// signal is how long ago the user told us.
const STALE_AFTER_MONTHS = 12;

export function monthsSince(isoDate, now = new Date()) {
  if (!isoDate) return null;
  const then = new Date(`${String(isoDate).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(then.getTime())) return null;
  const months = (now.getFullYear() - then.getFullYear()) * 12
    + (now.getMonth() - then.getMonth())
    - (now.getDate() < then.getDate() ? 1 : 0);
  return Math.max(0, months);
}

export function valuationNote(isoDate, now = new Date()) {
  const months = monthsSince(isoDate, now);
  if (months === null) return { text: 'Value never set — add one', warn: true };
  const age = months === 0 ? 'this month'
    : months === 1 ? '1 month ago'
      : `${months} months ago`;
  return months >= STALE_AFTER_MONTHS
    ? { text: `Valued ${age} — worth a refresh`, warn: true }
    : { text: `Valued ${age}`, warn: false };
}

// Row for a home / vehicle / other real asset. Unlike cash and investments
// the value has no feed behind it, so the row is where the user retypes it:
// committing a new value also stamps the valuation date. Equity is shown
// beside the value when a loan is linked; it is read from the summary and
// changes no total.
export default function AssetRow({ row, creditAccounts = [], onValueChange, onSecuredByChange }) {
  const note = valuationNote(row.valuationUpdatedOn);
  const meta = [];
  if (row.subtypeLabel) meta.push({ text: row.subtypeLabel });
  meta.push(note);
  const linked = row.securedByAccountId || '';
  const linkIsStale = !!linked && row.equity === null;

  return (
    <div className="acct-row acct-row--static">
      <div className="acct-row-avatar" aria-hidden="true">
        {GLYPHS[(row.subtype || '').toLowerCase()] || '🏷️'}
      </div>
      <div className="acct-row-body">
        <div className="acct-row-title">{row.name}</div>
        <MetaLine items={meta} />
        <div className="acct-row-secured">
          <select
            className="ifield"
            aria-label={`Secured by, for ${row.name}`}
            value={linked}
            onChange={(e) => onSecuredByChange?.(e.target.value || null)}
          >
            <option value="">Secured by — nothing</option>
            {creditAccounts.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          {linkIsStale && (
            <span className="acct-meta-warn">
              That loan is no longer here — equity unknown
            </span>
          )}
        </div>
      </div>
      <div className="acct-row-amount">
        <InlineField
          value={row.value}
          onChange={onValueChange}
          type="number"
          prefix="$"
          align="right"
          ariaLabel={`Value of ${row.name}`}
          placeholder={fmt$(0)}
        />
        {row.equity !== null && row.equity !== undefined && (
          <div className="acct-row-subamount">{fmt$(row.equity)} equity</div>
        )}
      </div>
      <div />
    </div>
  );
}
