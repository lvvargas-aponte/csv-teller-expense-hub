import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getUpcomingBills } from '../../../api/dashboard';
import { fmt$, fmtDate } from '../../../utils/formatting';

export default function UpcomingBillsCard({ onHide }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getUpcomingBills(30)
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load upcoming bills.'));
  }, []);

  const loading = data === null && !error;
  const bills = data?.bills || [];
  const empty = !loading && !error && bills.length === 0;

  return (
    <DashboardCard
      title="Upcoming Bills"
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No bills in the next 30 days. Set a due day on credit accounts (Accounts tab) to see them here."
      onHide={onHide}
    >
      <div style={{ display: 'grid', gap: 6 }}>
        {bills.map((b) => {
          const urgent = b.days_until <= 5;
          return (
            <div
              key={b.account_id}
              style={{
                display: 'flex', justifyContent: 'space-between',
                padding: '6px 0', fontSize: 13,
                borderBottom: '1px solid var(--border, #334155)',
              }}
            >
              <div>
                <div style={{ fontWeight: 500 }}>{b.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {fmtDate(b.due_date)}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: urgent ? '#f87171' : 'inherit', fontWeight: 600 }}>
                  in {b.days_until}d
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {fmt$(b.balance)}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
