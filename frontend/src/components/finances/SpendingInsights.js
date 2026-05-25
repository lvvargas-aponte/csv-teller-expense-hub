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
  const [revealed,         setRevealed]         = useState(false);
  const [transactions,     setTransactions]     = useState(null);
  const [accountDetails,   setAccountDetails]   = useState({});
  const [loading,          setLoading]          = useState(false);
  const [error,            setError]            = useState(null);

  // Lazy-load transactions + account details the first time the user reveals.
  // We don't refetch summary/dashboard — those are loaded once by the parent
  // FinancesPage and passed down as props.
  useEffect(() => {
    if (!revealed || transactions !== null) return;
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
  }, [revealed, transactions]);

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
        {!revealed && (
          <button
            type="button"
            className="ov-btn ov-btn-primary ov-btn-sm"
            onClick={() => setRevealed(true)}
          >
            ✨ Show Insights
          </button>
        )}
      </div>

      <div className="ov-card-body">
        {!revealed ? (
          <EmptyState onShow={() => setRevealed(true)} />
        ) : loading ? (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <Spin /> Loading insights…
          </div>
        ) : error ? (
          <div className="ov-error">{error}</div>
        ) : cards.length === 0 ? (
          <EmptyState
            onShow={() => setRevealed(true)}
            hideButton
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

function EmptyState({ onShow, hideButton, icon = '✨', title = 'Ready to surface insights', sub = "Get a plain-English summary of your spending patterns, wins, and areas to watch — generated from your transaction data." }) {
  return (
    <div className="ov-insights-empty">
      <div className="ov-insights-empty-icon">{icon}</div>
      <div className="ov-insights-empty-title">{title}</div>
      <div className="ov-insights-empty-sub">{sub}</div>
      {!hideButton && (
        <button type="button" className="ov-btn ov-btn-primary" onClick={onShow}>
          ✨ Show Insights
        </button>
      )}
    </div>
  );
}
