import React, { useEffect, useState } from 'react';
import axios from 'axios';
import DashboardCard from './DashboardCard';
import { fmt$ } from '../../../utils/formatting';

const API = process.env.REACT_APP_BACKEND_URL || '';

const PACE_COLOR = {
  ahead: '#10b981',
  on_track: '#10b981',
  behind: '#f59e0b',
  stalled: '#f87171',
};

export default function GoalsCard({ onHide }) {
  const [goals, setGoals] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    axios.get(`${API}/api/goals`)
      .then((r) => setGoals(r.data))
      .catch(() => setError('Could not load goals.'));
  }, []);

  const loading = goals === null && !error;
  const empty = !loading && !error && (!goals || goals.length === 0);

  return (
    <DashboardCard
      title="Goals"
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No goals set — add savings/emergency goals on the Plan tab."
      onHide={onHide}
    >
      <div style={{ display: 'grid', gap: 8 }}>
        {(goals || []).map((g) => {
          const pct = Math.min(100, g.progress_pct || 0);
          const paceColor = PACE_COLOR[g.pace_status] || 'var(--text-muted)';
          return (
            <div key={g.id} style={{ fontSize: 13 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 500 }}>{g.name}</span>
                <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>
                  {fmt$(g.current_balance)} / {fmt$(g.target_amount)}
                </span>
              </div>
              <div style={{ height: 6, background: 'var(--border, #334155)', borderRadius: 3, marginTop: 3 }}>
                <div style={{ height: '100%', width: `${pct}%`, background: '#6366f1', borderRadius: 3 }} />
              </div>
              {g.pace_status && (
                <div style={{ fontSize: 11, color: paceColor, marginTop: 2, textTransform: 'capitalize' }}>
                  {g.pace_status.replace('_', ' ')}
                  {g.monthly_required != null && ` · need ${fmt$(g.monthly_required)}/mo`}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
