import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getUpcomingBills } from '../../../api/dashboard';
import { fmt$, fmtDate } from '../../../utils/formatting';

export default function UpcomingBillsCard({ onHide, onNavigateToAccounts }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getUpcomingBills(30)
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load upcoming bills.'));
  }, []);

  const byKind = data?.total_due_by_kind;
  const loading = data === null && !error;
  const bills = data?.bills || [];
  const empty = !loading && !error && bills.length === 0;

  const emptyCta = onNavigateToAccounts ? (
    <div style={{ display: 'grid', gap: 8, padding: '8px 0' }}>
      <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>
        No bills in the next 30 days. Set a due day on each credit card to see what's coming up.
      </div>
      <button
        type="button"
        onClick={onNavigateToAccounts}
        style={{
          alignSelf: 'flex-start',
          padding: '6px 12px', borderRadius: 6,
          border: '1px solid var(--border)',
          background: 'transparent', cursor: 'pointer',
          fontSize: 12, fontWeight: 600,
        }}
      >
        Set due dates →
      </button>
    </div>
  ) : null;

  return (
    <DashboardCard
      title="Upcoming Bills"
      loading={loading}
      error={error}
      empty={empty && !emptyCta}
      emptyText="No bills in the next 30 days. Set a due day on credit accounts (Accounts tab) to see them here."
      onHide={onHide}
    >
      {empty && emptyCta}
      {!empty && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 22, fontWeight: 700 }}>{fmt$(data?.total_due ?? 0)}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            due in the next {data?.window_days ?? 30} days
            {byKind ? ` · ${fmt$(byKind.credit)} cards, ${fmt$(byKind.recurring)} bills` : ''}
          </div>
        </div>
      )}
      <div style={{ display: 'grid', gap: 6 }}>
        {bills.map((b, i) => {
          const urgent = b.days_until <= 5;
          return (
            <div
              key={b.account_id || b.merchant_key || `${b.due_date}-${i}`}
              style={{
                display: 'flex', justifyContent: 'space-between',
                padding: '6px 0', fontSize: 13,
                borderBottom: '1px solid var(--border)',
              }}
            >
              <div>
                <div style={{ fontWeight: 500 }}>{b.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {fmtDate(b.due_date)}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: urgent ? 'var(--status-bad-text)' : 'inherit', fontWeight: 600 }}>
                  {(b.amount_due !== null && b.amount_due !== undefined)
                    ? fmt$(b.amount_due)
                    : 'no minimum set'}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  in {b.days_until}d
                  {b.type !== 'recurring' && ` · ${fmt$(b.balance)} balance`}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
