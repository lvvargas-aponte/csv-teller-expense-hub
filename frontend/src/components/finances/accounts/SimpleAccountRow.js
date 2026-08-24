import React from 'react';
import { MetaLine } from './AccountListRow';
import { fmt$, formatRelativeTime } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';

// Read-only row for cash and investment accounts — same grid as the credit
// row, but not expandable (there is no un-synced metadata to edit). Cash
// account creation and balance edits still live on the Overview tab.
export default function SimpleAccountRow({
  row,
  glyph = '🏦',
  needsReconnect = false,
  cacheFetchedAt,
}) {
  const palette = chipColorFor(row.institution);

  const meta = [];
  if (row.institution) meta.push({ text: row.institution });
  if (row.manual) meta.push({ text: 'manual' });
  else if (needsReconnect) meta.push({ text: 'needs reconnect', warn: true });
  if (!row.manual && cacheFetchedAt) {
    meta.push({ text: `synced ${formatRelativeTime(cacheFetchedAt)}` });
  }

  return (
    <div className="acct-row acct-row--static">
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
      <div />
    </div>
  );
}
