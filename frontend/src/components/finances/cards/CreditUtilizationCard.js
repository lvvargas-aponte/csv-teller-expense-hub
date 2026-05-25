import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getCreditHealth } from '../../../api/dashboard';
import Num from '../Num';

const STATUS_COLOR = {
  good: '#059669',
  warn: '#f59e0b',
  high: '#ef4444',
  unknown: 'var(--text-muted)',
};

export default function CreditUtilizationCard({ onHide, index, kicker }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCreditHealth()
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load credit utilization.'));
  }, []);

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
