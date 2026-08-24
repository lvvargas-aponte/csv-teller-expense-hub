import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import Spin from '../ui/Spin';
import { API_BASE } from '../../utils/formatting';
import { buildInsights } from '../../utils/insightBuilder';
import { getAllAccountDetails } from '../../api/accountDetails';

export default function SpendingInsights({
  summary,
  dashboard,
  onNavigate,
}) {
  const [transactions,     setTransactions]     = useState(null);
  const [accountDetails,   setAccountDetails]   = useState({});
  const [loading,          setLoading]          = useState(true);
  const [error,            setError]            = useState(null);

  // The one section that interprets rather than reports used to sit behind a
  // "✨ Show Insights" click. Transactions and account details now load with
  // the rest of the grid; summary/dashboard arrive as props, fetched once.
  useEffect(() => {
    if (transactions !== null) return;
    setLoading(true);
    setError(null);
    Promise.all([
      axios.get(`${API_BASE}/api/transactions/all`),
      getAllAccountDetails().catch(() => ({ data: {} })),
    ])
      .then(([txRes, detRes]) => {
        setTransactions(txRes.data || []);
        setAccountDetails(detRes.data || {});
      })
      .catch(() => setError('Could not load insights — is the backend running?'))
      .finally(() => setLoading(false));
  }, [transactions]);

  const cards = useMemo(
    () => buildInsights({
      summary,
      dashboard,
      transactions: transactions ?? [],
      accountDetails,
    }),
    [summary, dashboard, transactions, accountDetails]
  );

  const handleAction = (target) => {
    if (!target || !onNavigate) return;
    onNavigate(target);
  };

  return (
    <div className="ov-card">
      <div className="ov-card-header">
        <div>
          <div className="ov-card-title">Spending Insights</div>
          <div className="ov-card-subtitle">Observations drawn from your latest data</div>
        </div>
      </div>

      <div className="ov-card-body">
        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <Spin /> Loading insights…
          </div>
        ) : error ? (
          <div className="ov-error">{error}</div>
        ) : cards.length === 0 ? (
          <EmptyState
            icon="🌱"
            title="No insights yet"
            sub="Once you have a couple of months of transactions, we'll surface trends, wins, and things to watch."
          />
        ) : (
          <div>
            {cards.map((c) => (
              <div key={c.id} className="ov-insight-card">
                <div className="ov-insight-icon" style={{ background: c.iconBg }}>{c.icon}</div>
                <div className="ov-insight-body-col">
                  <div className="ov-insight-title-row">
                    <div className="ov-insight-title">{c.title}</div>
                    <span className={`ov-tag ${c.tagClass}`}>{c.tag}</span>
                  </div>
                  <div className="ov-insight-body">{c.body}</div>
                  {c.action && (
                    <button
                      type="button"
                      className="ov-insight-action"
                      onClick={() => handleAction(c.action.target)}
                    >
                      {c.action.label}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState({ icon, title, sub }) {
  return (
    <div className="ov-insights-empty">
      <div className="ov-insights-empty-icon">{icon}</div>
      <div className="ov-insights-empty-title">{title}</div>
      <div className="ov-insights-empty-sub">{sub}</div>
    </div>
  );
}
