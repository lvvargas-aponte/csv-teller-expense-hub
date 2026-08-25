import React from 'react';
import { MetaLine } from './AccountListRow';
import { fmt$, formatRelativeTime } from '../../../utils/formatting';
import { chipColorFor } from '../../../utils/institutionColor';

export const TAX_TREATMENT_OPTIONS = [
  { value: '',            label: 'Not set' },
  { value: 'taxable',     label: 'Taxable — already-taxed money' },
  { value: 'traditional', label: 'Traditional — taxed on withdrawal' },
  { value: 'roth',        label: 'Roth — tax-free on withdrawal' },
  { value: 'hsa',         label: 'HSA' },
  { value: 'education',   label: 'Education (529)' },
  { value: 'other',       label: 'Other' },
];

const TREATMENT_LABEL = {
  taxable: 'taxable', traditional: 'traditional', roth: 'Roth',
  hsa: 'HSA', education: 'education', other: 'other',
};

// Read-only row for cash and investment accounts — same grid as the credit
// row, but not expandable (there is no un-synced metadata to edit). Cash
// account creation and balance edits still live on the Overview tab.
//
// Investment rows carry one editable field: how the balance is taxed. It is
// prefilled from the subtype and says so until the user confirms it, because
// a Roth 401(k) and a traditional one look identical in every feed.
export default function SimpleAccountRow({
  row,
  glyph = '🏦',
  needsReconnect = false,
  cacheFetchedAt,
  taxTreatment = null,
  onTaxTreatmentChange,
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
        {taxTreatment && (
          <div className="acct-row-secured">
            <select
              className="ifield"
              aria-label={`Tax treatment, for ${row.name}`}
              value={taxTreatment.treatment || ''}
              onChange={(e) => onTaxTreatmentChange?.(e.target.value || null)}
            >
              {TAX_TREATMENT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            {!taxTreatment.setByUser && taxTreatment.inferred && (
              <span className="acct-row-assumed">
                assumed {TREATMENT_LABEL[taxTreatment.inferred] || taxTreatment.inferred}
                {' '}— is that right?
              </span>
            )}
          </div>
        )}
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
