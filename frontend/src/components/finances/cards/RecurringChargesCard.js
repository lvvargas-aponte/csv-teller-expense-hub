import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import Num from '../Num';
import { getDashboard } from '../../../api/dashboard';

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

export function pickIcon(description = '', category = '') {
  const haystack = `${description} ${category}`;
  for (const rule of ICON_RULES) {
    if (rule.test.test(haystack)) return { icon: rule.icon, color: rule.color };
  }
  return { icon: '🔁', color: '#d1fae5' };
}

// Try to extract a friendly name + institution detail from the description.
// Backend gives us things like "AMEX EPAYMENT 8005" or "MORTGAGE TRUIST" —
// we strip trailing digits/codes and title-case the rest.
export function prettifyName(description = '') {
  return description
    .replace(/\b\d{4,}\b/g, '')           // long digit codes
    .replace(/\b(EPAYMENT|ACH|XFER|PYMT)\b/gi, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

// Categories that belong to Upcoming Bills (shown above on the Bills page),
// so they shouldn't repeat in the Recurring Charges section. Mirrors the
// backend ``BILL_CATEGORIES`` allowlist in ``routers/bills.py``.
const BILL_CATEGORIES = new Set(['utilities', 'mortgage', 'rent']);

// "Obviously needed" essentials — necessary spending that happens to repeat
// monthly, but isn't a subscription or commitment the user can cancel. Filter
// these out of the Bills-page Recurring Charges view so the list only shows
// optional/managed commitments (insurance, subscriptions, therapy, etc.).
const ESSENTIAL_CATEGORIES = new Set([
  'groceries', 'grocery', 'gas', 'fuel', 'restaurants', 'restaurant',
  'fast food', 'dining', 'food & dining', 'food and dining', 'coffee',
  'transit', 'parking', 'rideshare', 'taxi', 'uber', 'lyft',
  'general', 'uncategorized',
]);

// Project the next occurrence of a merchant's typical day-of-month, given the
// last-seen date. Mirrors backend ``_next_due_date`` so the Bills detail view
// shows the same "next due" the API would.
function projectNext(lastSeenStr, typicalDay) {
  if (!lastSeenStr || !typicalDay) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  let y = today.getFullYear();
  let m = today.getMonth();
  const lastDay = (yy, mm) => new Date(yy, mm + 1, 0).getDate();
  let d = Math.min(typicalDay, lastDay(y, m));
  let candidate = new Date(y, m, d);
  if (candidate < today) {
    m += 1;
    if (m === 12) { y += 1; m = 0; }
    d = Math.min(typicalDay, lastDay(y, m));
    candidate = new Date(y, m, d);
  }
  const daysUntil = Math.round((candidate - today) / (1000 * 60 * 60 * 24));
  return { date: candidate, daysUntil };
}

export default function RecurringChargesCard({ dashboard, loading, error, index, kicker, variant = 'compact' }) {
  // Self-fetch when used outside the Dashboard (e.g. the Bills page renders
  // this card standalone and doesn't pass the dashboard prop).
  const [selfData, setSelfData] = useState(null);
  const [selfErr, setSelfErr] = useState(null);
  const selfFetch = dashboard === undefined && !loading && !error;
  useEffect(() => {
    if (!selfFetch) return;
    let cancelled = false;
    getDashboard(6)
      .then((r) => { if (!cancelled) setSelfData(r.data); })
      .catch(() => { if (!cancelled) setSelfErr('Could not load recurring charges.'); });
    return () => { cancelled = true; };
  }, [selfFetch]);

  const data = dashboard ?? selfData;
  const effectiveLoading = loading || (selfFetch && !selfData && !selfErr);
  const effectiveError = error || selfErr;
  const rawCharges = data?.recurring_charges || [];
  // On the Bills page (variant='detail'), drop charges that are already shown
  // in the Upcoming Bills card above, and drop daily essentials (groceries,
  // gas, dining, etc.) that aren't manageable commitments. Dashboard keeps
  // the full list.
  const charges = variant === 'detail'
    ? rawCharges.filter((c) => {
        const cat = (c.category || '').trim().toLowerCase();
        if (BILL_CATEGORIES.has(cat)) return false;
        if (ESSENTIAL_CATEGORIES.has(cat)) return false;
        return true;
      })
    : rawCharges;
  const empty = !effectiveLoading && !effectiveError && charges.length === 0;
  const total = charges.reduce((s, c) => s + (c.estimated_monthly_cost || 0), 0);

  return (
    <DashboardCard
      title="Recurring Charges"
      index={index}
      kicker={kicker}
      loading={effectiveLoading}
      error={effectiveError}
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
          Monthly commitments · <Num value={total} /> total
        </div>
      )}
      {variant === 'detail' ? (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: 'left', color: 'var(--text-muted)', fontSize: 11 }}>
              <th style={{ padding: '6px 8px 6px 0' }}>Merchant</th>
              <th style={{ padding: '6px 8px' }}>Category</th>
              <th style={{ padding: '6px 8px' }}>Cadence</th>
              <th style={{ padding: '6px 8px' }}>Last seen</th>
              <th style={{ padding: '6px 8px' }}>Next due</th>
              <th style={{ padding: '6px 0 6px 8px', textAlign: 'right' }}>Monthly</th>
            </tr>
          </thead>
          <tbody>
            {[...charges]
              .map((c) => ({ c, next: projectNext(c.last_seen, c.typical_day) }))
              .sort((a, b) => {
                const da = a.next ? a.next.daysUntil : 9999;
                const db = b.next ? b.next.daysUntil : 9999;
                return da - db;
              })
              .map(({ c, next }, i) => {
                const { icon, color } = pickIcon(c.sample_description, c.category);
                const name = prettifyName(c.sample_description);
                const dueLabel = next ? next.date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
                const daysLabel = next ? (next.daysUntil === 0 ? 'today' : `in ${next.daysUntil}d`) : '';
                const urgent = next && next.daysUntil <= 5;
                return (
                  <tr key={`${c.merchant_key}-${i}`} style={{ borderTop: '1px solid var(--border, #334155)' }}>
                    <td style={{ padding: '8px 8px 8px 0' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{
                          width: 28, height: 28, borderRadius: 6,
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          background: color, fontSize: 14, flexShrink: 0,
                        }}>{icon}</span>
                        <span style={{ fontWeight: 600 }}>{name}</span>
                      </div>
                    </td>
                    <td style={{ padding: '8px', color: 'var(--text-muted)' }}>
                      {c.category && c.category !== 'Uncategorized' ? c.category : '—'}
                    </td>
                    <td style={{ padding: '8px', color: 'var(--text-muted)' }}>
                      {c.months_seen}/{c.occurrences} mo · day {c.typical_day || '?'}
                    </td>
                    <td style={{ padding: '8px', color: 'var(--text-muted)' }}>{c.last_seen}</td>
                    <td style={{ padding: '8px' }}>
                      <div style={{ fontWeight: 600 }}>{dueLabel}</div>
                      {daysLabel && (
                        <div style={{ fontSize: 11, color: urgent ? 'var(--status-bad-text)' : 'var(--text-muted)' }}>
                          {daysLabel}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '8px 0 8px 8px', textAlign: 'right', fontFamily: "'DM Mono', monospace", fontWeight: 700 }}>
                      <Num value={c.estimated_monthly_cost} />
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      ) : (
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
                  <Num value={c.estimated_monthly_cost} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </DashboardCard>
  );
}
