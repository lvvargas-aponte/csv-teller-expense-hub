import React, { useMemo } from 'react';
import UtilBar, { utilColor } from './UtilBar';

// Mortgages and installment loans are typed 'credit' (they're liabilities)
// but have a principal, not a credit limit — utilization doesn't apply.
const LOAN_KEYWORDS = ['loan', 'mortgage'];
const isLoan = (a) => {
  const text = (a.subtype || a.name || '').toLowerCase().replace('credit union', '');
  return LOAN_KEYWORDS.some((kw) => text.includes(kw));
};

// Per-card utilization plus an overall headline. Filters out loans, and cards
// with no limit set (otherwise we can't compute a percentage).
export default function UtilSummaryCard({ creditAccounts, detailsMap }) {
  const rows = useMemo(() => {
    return creditAccounts
      .filter((a) => !isLoan(a))
      .map((a) => {
        const d = detailsMap[a.id] || {};
        const limit = (d.credit_limit !== null && d.credit_limit !== undefined) ? parseFloat(d.credit_limit) : null;
        if (!limit || limit <= 0) return null;
        const owed = parseFloat(a.ledger) || 0;
        return { id: a.id, name: a.name, owed, limit, pct: (owed / limit) * 100 };
      })
      .filter(Boolean);
  }, [creditAccounts, detailsMap]);

  const overall = useMemo(() => {
    if (!rows.length) return null;
    const sumOwed  = rows.reduce((s, r) => s + r.owed, 0);
    const sumLimit = rows.reduce((s, r) => s + r.limit, 0);
    return sumLimit > 0 ? (sumOwed / sumLimit) * 100 : null;
  }, [rows]);

  if (!rows.length) return null;

  return (
    <div className="acct-rail-card">
      <div className="acct-rail-header">
        <h3 className="acct-rail-title">Credit Utilization</h3>
        {(overall !== null && overall !== undefined) && (
          <span
            className="acct-rail-overall"
            style={{ color: utilColor(overall) }}
          >
            {Math.round(overall)}%
          </span>
        )}
      </div>
      <div className="acct-util-list">
        {rows.map((r) => {
          const over = r.pct > 100;
          return (
            <div key={r.id} className="acct-util-row">
              <span className="acct-util-name">
                {r.name}
                {over && (
                  <span
                    style={{
                      marginLeft: 6,
                      padding: '1px 6px',
                      fontSize: 10,
                      fontWeight: 600,
                      color: '#b91c1c',
                      background: '#fef2f2',
                      border: '1px solid #fecaca',
                      borderRadius: 4,
                      whiteSpace: 'nowrap',
                    }}
                    title={`Balance exceeds limit by $${Math.round(r.owed - r.limit)}`}
                  >
                    Over limit
                  </span>
                )}
              </span>
              <div className="acct-util-bar-wrap">
                <UtilBar pct={r.pct} showLabel={false} />
              </div>
              <span className="acct-util-pct" style={{ color: utilColor(r.pct) }}>
                {Math.round(r.pct)}%
              </span>
            </div>
          );
        })}
      </div>
      <div className="acct-rail-tip">
        Keep utilization below 30% per card for the best credit score impact.
      </div>
    </div>
  );
}
