import React from 'react';
import DashboardCard from './DashboardCard';
import Num from '../Num';

export default function BalancesCard({ summary, loading, error, onHide, index, kicker }) {
  const accounts = summary?.accounts || [];
  const empty = !loading && !error && accounts.length === 0;

  return (
    <DashboardCard
      title="Account Balances"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No accounts yet — connect via SimpleFIN or add manually on the Accounts tab."
      onHide={onHide}
    >
      {summary && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Net Worth</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: summary.net_worth >= 0 ? 'var(--status-good-text)' : 'var(--status-bad-text)' }}>
            <Num value={summary.net_worth} signed />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Cash <Num value={summary.total_cash || 0} /> · Credit <Num value={summary.total_credit_debt || 0} />
            {(summary.total_investments || 0) > 0 && <> · Invest <Num value={summary.total_investments} /></>}
          </div>
        </div>
      )}
      <div style={{ display: 'grid', gap: 6 }}>
        {accounts.slice(0, 8).map((a) => (
          <div key={a.id}
               style={{
                 display: 'flex', justifyContent: 'space-between',
                 fontSize: 13, padding: '4px 0',
                 borderBottom: '1px solid var(--border, #334155)',
               }}>
            <div>
              <div style={{ fontWeight: 500 }}>{a.name}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{a.institution}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              {a.type === 'credit'
                ? (() => {
                    const owed = parseFloat(a.ledger) || 0;
                    const hasDebt = Math.round(owed * 100) !== 0;
                    return (
                      <span style={{ color: hasDebt ? 'var(--status-bad-text)' : 'var(--text-muted)', fontFamily: "'DM Mono', monospace", fontWeight: 700 }}>
                        {hasDebt ? <Num value={owed} prefix="-" /> : <Num value={0} />}
                      </span>
                    );
                  })()
                : <span style={{ color: 'var(--status-good-text)', fontFamily: "'DM Mono', monospace", fontWeight: 700 }}>
                    <Num value={a.available || 0} />
                  </span>}
            </div>
          </div>
        ))}
        {accounts.length > 8 && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center' }}>
            + {accounts.length - 8} more on Accounts tab
          </div>
        )}
      </div>
    </DashboardCard>
  );
}
