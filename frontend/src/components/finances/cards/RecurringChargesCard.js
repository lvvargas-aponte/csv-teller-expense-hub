import React from 'react';
import DashboardCard from './DashboardCard';
import { fmt$ } from '../../../utils/formatting';

// Match a transaction description / category to an emoji + tinted background.
// Order matters — first match wins.
const ICON_RULES = [
  { test: /mortgage|rent|housing/i,             icon: '🏠', color: '#dbeafe' },
  { test: /savings|transfer|invest/i,           icon: '💰', color: '#d1fae5' },
  { test: /amex|payment|card|visa|mastercard/i, icon: '💳', color: '#fef3c7' },
  { test: /health|medical|insurance.*health/i,  icon: '🏥', color: '#fce7f3' },
  { test: /therapy|psych|counsel/i,             icon: '🧠', color: '#ede9fe' },
  { test: /car|auto|progressive|geico/i,        icon: '🚗', color: '#e0f2fe' },
  { test: /utilit|electric|gas|water|power/i,   icon: '⚡', color: '#fef9c3' },
  { test: /spotify|netflix|hulu|disney|stream/i,icon: '🎬', color: '#fce7f3' },
  { test: /gym|fitness|peloton/i,               icon: '🏋️', color: '#d1fae5' },
  { test: /phone|wireless|verizon|att|t.?mobile/i, icon: '📱', color: '#dbeafe' },
];

function pickIcon(description = '', category = '') {
  const haystack = `${description} ${category}`;
  for (const rule of ICON_RULES) {
    if (rule.test.test(haystack)) return { icon: rule.icon, color: rule.color };
  }
  return { icon: '🔁', color: '#d1fae5' };
}

// Try to extract a friendly name + institution detail from the description.
// Backend gives us things like "AMEX EPAYMENT 8005" or "MORTGAGE TRUIST" —
// we strip trailing digits/codes and title-case the rest.
function prettifyName(description = '') {
  return description
    .replace(/\b\d{4,}\b/g, '')           // long digit codes
    .replace(/\b(EPAYMENT|ACH|XFER|PYMT)\b/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function RecurringChargesCard({ dashboard, loading, error }) {
  const charges = dashboard?.recurring_charges || [];
  const empty = !loading && !error && charges.length === 0;
  const total = charges.reduce((s, c) => s + (c.estimated_monthly_cost || 0), 0);

  return (
    <DashboardCard
      title="Recurring Charges"
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No recurring charges detected yet (need ≥2 months of similar charges)."
      headerExtra={
        charges.length > 0 ? (
          <span style={{
            fontSize: 10, fontWeight: 700,
            textTransform: 'uppercase', letterSpacing: '0.04em',
            padding: '2px 8px', borderRadius: 99,
            background: '#fef3c7', color: '#f59e0b',
          }}>
            {charges.length} detected
          </span>
        ) : null
      }
    >
      {charges.length > 0 && (
        <div style={{
          fontSize: 11, color: 'var(--text-muted)',
          marginTop: -4, marginBottom: 8,
        }}>
          Monthly commitments · {fmt$(total)} total
        </div>
      )}
      <div className="eh-recurring-grid">
        {charges.map((c, i) => {
          const { icon, color } = pickIcon(c.sample_description, c.category);
          const name = prettifyName(c.sample_description);
          const detail = c.category && c.category !== 'Uncategorized'
            ? c.category
            : `${c.months_seen || 0} months · ${c.occurrences || 0} charges`;
          return (
            <div key={`${c.merchant_key}-${i}`} className="eh-recurring-row">
              <div className="eh-recurring-icon" style={{ background: color }}>{icon}</div>
              <div className="eh-recurring-info">
                <div className="eh-recurring-name">{name}</div>
                <div className="eh-recurring-detail">{detail}</div>
              </div>
              <div className="eh-recurring-amount">
                {fmt$(c.estimated_monthly_cost)}
              </div>
            </div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
