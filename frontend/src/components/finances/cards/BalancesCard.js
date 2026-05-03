import React from 'react';
import DashboardCard from './DashboardCard';
import { fmt$, fmtSigned } from '../../../utils/formatting';

export default function BalancesCard({ summary, loading, error, onHide }) {
  const accounts = summary?.accounts || [];
  const empty = !loading && !error && accounts.length === 0;

  return (
    <DashboardCard
      title="Account Balances"
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No accounts yet — connect via Teller or add manually on the Accounts tab."
      onHide={onHide}
    >
      {summary && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Net Worth</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: summary.net_worth >= 0 ? '#059669' : '#ef4444' }}>
            {fmtSigned(summary.net_worth)}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
            Cash {fmt$(summary.total_cash || 0)} · Credit {fmt$(summary.total_credit_debt || 0)}
            {(summary.total_investments || 0) > 0 && <> · Invest {fmt$(summary.total_investments)}</>}
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
                ? <span style={{ color: '#ef4444', fontFamily: "'DM Mono', monospace", fontWeight: 700 }}>
                    -{fmt$(a.ledger || 0)}
                  </span>
                : <span style={{ color: '#059669', fontFamily: "'DM Mono', monospace", fontWeight: 700 }}>
                    {fmt$(a.available || 0)}
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
