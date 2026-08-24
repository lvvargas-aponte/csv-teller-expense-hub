import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getCreditHealth } from '../../../api/dashboard';
import Num from '../Num';
import { fmt$ } from '../../../utils/formatting';

const STATUS_COLOR = {
  good: '#059669',
  warn: '#f59e0b',
  high: '#ef4444',
  unknown: 'var(--text-muted)',
};

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
            color: STATUS_COLOR[data.overall_status] || 'inherit',
          }}>
            {data.overall_utilization_pct}%
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
          const color = STATUS_COLOR[a.status] || 'inherit';
          return (
            <div key={a.account_id} style={{ fontSize: 13 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 500 }}>{a.name || a.institution}</span>
                <span style={{ color, fontSize: 12 }}>
                  {(pct !== null && pct !== undefined) ? `${pct}%` : 'set limit →'}
                </span>
              </div>
              <div style={{ height: 6, background: 'var(--border, #334155)', borderRadius: 3, marginTop: 3 }}>
                <div style={{ height: '100%', width: `${barWidth}%`, background: color, borderRadius: 3 }} />
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
