import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import Num from '../Num';
import { listBudgets } from '../../../api/budgets';

export default function BudgetsCard({ onHide, index, kicker }) {
  const [budgets, setBudgets] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    listBudgets()
      .then((r) => setBudgets(r.data))
      .catch(() => setError('Could not load budgets.'));
  }, []);

  const loading = budgets === null && !error;
  const empty = !loading && !error && (!budgets || budgets.length === 0);

  return (
    <DashboardCard
      title="Budgets"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No budgets set — add categories on the Plan tab."
      onHide={onHide}
    >
      <div style={{ display: 'grid', gap: 8 }}>
        {(budgets || []).map((b) => {
          const pct = Math.min(100, b.percent_used || 0);
          const fill = b.over_budget ? 'var(--red)' : pct >= 90 ? 'var(--amber)' : 'var(--accent)';
          const text = b.over_budget
            ? 'var(--status-bad-text)'
            : pct >= 90 ? 'var(--status-warn-text)' : 'var(--status-good-text)';
          const word = b.over_budget ? 'Over budget' : pct >= 90 ? 'Close to limit' : 'On track';
          return (
            <div key={b.category} style={{ fontSize: 13 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 500 }}>{b.category}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  <Num value={b.current_month_spent} /> / <Num value={b.monthly_limit} />
                  <span style={{ color: text, fontWeight: 600, marginLeft: 6 }}>{word}</span>
                </span>
              </div>
              <div
                style={{ height: 6, background: 'var(--border)', borderRadius: 3, marginTop: 3 }}
                role="progressbar"
                aria-label={`${b.category} budget`}
                aria-valuenow={Math.round(pct)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuetext={`${Math.round(b.percent_used || 0)}% used — ${word}`}
              >
                <div style={{ height: '100%', width: `${pct}%`, background: fill, borderRadius: 3 }} />
              </div>
            </div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
