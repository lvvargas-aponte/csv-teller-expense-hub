import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getCreditHealth } from '../../../api/dashboard';
import Num from '../Num';
import { fmt$ } from '../../../utils/formatting';

// Bars keep the saturated fill; the figure beside them uses the text-grade
// sibling and carries the band as a word, so the band survives both a
// colour-blind reader and a greyscale print.
const STATUS_FILL = {
  good: 'var(--accent)',
  warn: 'var(--amber)',
  high: 'var(--red)',
  unknown: 'var(--text-muted)',
};

const STATUS_TEXT = {
  good: 'var(--status-good-text)',
  warn: 'var(--status-warn-text)',
  high: 'var(--status-bad-text)',
  unknown: 'var(--text-muted)',
};

const STATUS_WORD = { good: 'Good', warn: 'Watch', high: 'High' };

export default function CreditUtilizationCard({ onHide, index, kicker, onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCreditHealth()
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load credit utilization.'));
  }, []);

  const carry = data?.carry_cost;
  const loading = data === null && !error;
  const accounts = data?.accounts || [];
  const empty = !loading && !error && accounts.length === 0;

  return (
    <DashboardCard
      title="Credit Utilization"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No credit cards found. Add credit limits on the Accounts tab to see utilization."
      onHide={onHide}
    >
      {carry?.monthly_interest > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>
            Your debt costs about ${Math.round(carry.monthly_interest).toLocaleString()}/month
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            {fmt$(carry.annual_interest)} a year in interest at current balances
          </div>
        </div>
      )}
      {carry?.accounts_missing_apr > 0 && (
        <button
          type="button"
          onClick={() => onNavigate?.('accounts')}
          style={{
            display: 'block', marginBottom: 10, padding: 0,
            background: 'none', border: 'none', font: 'inherit',
            fontSize: 11, color: 'var(--accent)',
            textDecoration: 'underline', cursor: 'pointer', textAlign: 'left',
          }}
        >
          {carry.accounts_missing_apr} card{carry.accounts_missing_apr === 1 ? '' : 's'}
          {' '}have no APR set — add one to see their cost
        </button>
      )}
      {(data?.overall_utilization_pct !== null && data?.overall_utilization_pct !== undefined) && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Overall</div>
          <div style={{
            fontSize: 20, fontWeight: 700,
            color: STATUS_TEXT[data.overall_status] || 'inherit',
          }}>
            {data.overall_utilization_pct}%
            {STATUS_WORD[data.overall_status] && (
              <span style={{ fontSize: 12, fontWeight: 600, marginLeft: 6 }}>
                {STATUS_WORD[data.overall_status]}
              </span>
            )}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            <Num value={data.total_balance} /> of <Num value={data.total_limit} />
          </div>
        </div>
      )}
      <div style={{ display: 'grid', gap: 8 }}>
        {accounts.map((a) => {
          const pct = a.utilization_pct;
          const barWidth = (pct === null || pct === undefined) ? 0 : Math.min(100, pct);
          const fill = STATUS_FILL[a.status] || 'inherit';
          const word = STATUS_WORD[a.status];
          return (
            <div key={a.account_id} style={{ fontSize: 13 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 500 }}>{a.name || a.institution}</span>
                <span style={{ color: STATUS_TEXT[a.status] || 'inherit', fontSize: 12 }}>
                  {(pct !== null && pct !== undefined) ? `${pct}%` : 'set limit →'}
                  {word && <span style={{ marginLeft: 6, fontWeight: 600 }}>{word}</span>}
                </span>
              </div>
              <div
                style={{ height: 6, background: 'var(--border, #334155)', borderRadius: 3, marginTop: 3 }}
                role="progressbar"
                aria-label={`${a.name || a.institution} utilization`}
                aria-valuenow={barWidth}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuetext={word ? `${pct}% used — ${word}` : `${pct}% used`}
              >
                <div style={{ height: '100%', width: `${barWidth}%`, background: fill, borderRadius: 3 }} />
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                <Num value={a.balance} />{(a.credit_limit !== null && a.credit_limit !== undefined) && <> / <Num value={a.credit_limit} /></>}
              </div>
            </div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
