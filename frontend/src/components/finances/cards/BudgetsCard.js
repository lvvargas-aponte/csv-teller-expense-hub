import React, { useEffect, useState } from 'react';
import axios from 'axios';
import DashboardCard from './DashboardCard';
import { fmt$ } from '../../../utils/formatting';

const API = process.env.REACT_APP_BACKEND_URL || '';

export default function BudgetsCard({ onHide }) {
  const [budgets, setBudgets] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios.get(`${API}/api/budgets`)
      .then((r) => setBudgets(r.data))
      .catch(() => setError('Could not load budgets.'));
  }, []);

  const loading = budgets === null && !error;
  const empty = !loading && !error && (!budgets || budgets.length === 0);

  return (
    <DashboardCard
      title="Budgets"
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No budgets set — add categories on the Plan tab."
      onHide={onHide}
    >
      <div style={{ display: 'grid', gap: 8 }}>
        {(budgets || []).map((b) => {
          const pct = Math.min(100, b.percent_used || 0);
          const color = b.over_budget ? '#ef4444' : pct >= 90 ? '#f59e0b' : '#059669';
          return (
            <div key={b.category} style={{ fontSize: 13 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 500 }}>{b.category}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  {fmt$(b.current_month_spent)} / {fmt$(b.monthly_limit)}
                </span>
              </div>
              <div style={{ height: 6, background: 'var(--border, #334155)', borderRadius: 3, marginTop: 3 }}>
                <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3 }} />
              </div>
            </div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
