import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getCashflowProjection } from '../../../api/cashflow';
import Num, { BlurMoney } from '../Num';

// Bars keep the saturated fill; the figures beside them use the text-grade
// sibling, which is the only one that clears 4.5:1 on the white card.
const IN_FILL = 'var(--accent)';
const OUT_FILL = 'var(--amber)';
const NEG_FILL = 'var(--red)';
const IN_TEXT = 'var(--status-good-text)';
const OUT_TEXT = 'var(--status-warn-text)';
const NEG_TEXT = 'var(--status-bad-text)';

const CONFIDENCE_NOTE = {
  high: 'median of your last three complete months',
  low: 'rough — two months of history',
};

export default function CashFlowOutlookCard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCashflowProjection(30)
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load the cash-flow outlook.'));
  }, []);

  const loading = data === null && !error;
  const horizon = data?.horizon_days ?? 30;
  const moneyIn = (data?.expected_income || 0) + (data?.expected_inbound_transfers || 0);
  const recurring = data?.expected_recurring_outflow || 0;
  const discretionary = data?.expected_discretionary_outflow || 0;
  const net = data?.net || 0;
  const confidence = data?.discretionary_basis?.confidence;
  const incomplete = data?.projection_incomplete === true;
  const empty = !loading && !error && moneyIn === 0 && recurring === 0 && discretionary === 0;

  const rows = [
    { key: 'in', label: 'Money in', value: moneyIn, fill: IN_FILL, text: IN_TEXT },
    { key: 'recurring', label: 'Recurring bills', value: -recurring, fill: OUT_FILL, text: OUT_TEXT },
  ];
  if (!incomplete) {
    rows.push({
      key: 'discretionary',
      label: 'Typical spending',
      value: -discretionary,
      fill: OUT_FILL,
      text: OUT_TEXT,
      note: CONFIDENCE_NOTE[confidence],
    });
  }
  rows.push({
    key: 'net',
    label: 'Projected net',
    value: net,
    fill: net < 0 ? NEG_FILL : IN_FILL,
    text: net < 0 ? NEG_TEXT : IN_TEXT,
    emphasis: true,
  });

  const widest = Math.max(...rows.map((r) => Math.abs(r.value)), 1);

  return (
    <DashboardCard
      title={`${horizon}-Day Outlook`}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="Not enough history yet to project the next month."
    >
      <div style={{ display: 'grid', gap: 10 }}>
        {rows.map((r) => (
          <div key={r.key}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <span style={{ fontWeight: r.emphasis ? 700 : 500 }}>{r.label}</span>
              <span style={{ color: r.text, fontWeight: r.emphasis ? 700 : 500 }}>
                <Num value={r.value} signed prefix={r.value >= 0 ? '+' : ''} />
                <span className="sr-only">{r.value < 0 ? ' out' : ' in'}</span>
              </span>
            </div>
            <div
              style={{ height: 6, background: 'var(--border, #334155)', borderRadius: 3, marginTop: 3 }}
              aria-hidden="true"
            >
              <div style={{
                height: '100%',
                width: `${Math.min(100, (Math.abs(r.value) / widest) * 100)}%`,
                background: r.fill,
                borderRadius: 3,
              }} />
            </div>
            {r.note && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{r.note}</div>
            )}
          </div>
        ))}
      </div>

      {net < 0 && (
        <div style={{ fontSize: 12, color: NEG_TEXT, marginTop: 10, fontWeight: 600 }}>
          <BlurMoney
            text={`Spending is projected to exceed income by about $${Math.round(Math.abs(net)).toLocaleString()} over the next ${horizon} days.`}
          />
        </div>
      )}

      {incomplete && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 10 }}>
          Typical spending isn&apos;t counted yet — under two complete months of history, so this
          projection is incomplete and covers bills only.
        </div>
      )}

      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 10 }}>
        An estimate from your recent months, not a promise. Bills are projected from the day of
        the month each one usually lands.
      </div>
    </DashboardCard>
  );
}
