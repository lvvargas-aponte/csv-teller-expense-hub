import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getAlerts } from '../../../api/dashboard';
import { BlurMoney } from '../Num';

const SEVERITY = {
  error: { color: '#ef4444', icon: '!' },
  warn:  { color: '#f59e0b', icon: '⚠' },
  info:  { color: '#059669', icon: 'i' },
};

export default function AlertsCard({ onHide, index, kicker, onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getAlerts()
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load alerts.'));
  }, []);

  const loading = data === null && !error;
  const alerts = data?.alerts || [];
  const empty = !loading && !error && alerts.length === 0;

  return (
    <DashboardCard
      title="Alerts & Insights"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="All clear — no alerts."
      onHide={onHide}
    >
      <div style={{ display: 'grid', gap: 6 }}>
        {alerts.map((a, i) => {
          const sev = SEVERITY[a.severity] || SEVERITY.info;
          // An alert nobody can act on is just a notification. Where the feed
          // names a tab, the whole row is the way there.
          const actionable = Boolean(a.tab && onNavigate);
          const rowStyle = {
            display: 'flex',
            gap: 8,
            padding: '6px 8px',
            borderLeft: `3px solid ${sev.color}`,
            background: 'var(--bg-secondary)',
            fontSize: 13,
            textAlign: 'left',
            width: '100%',
            font: 'inherit',
            border: 'none',
            borderLeftWidth: 3,
            borderLeftStyle: 'solid',
            borderLeftColor: sev.color,
            cursor: actionable ? 'pointer' : 'default',
          };
          const content = (
            <>
              <span style={{ color: sev.color, fontWeight: 700 }}>{sev.icon}</span>
              <span><BlurMoney text={a.message} /></span>
            </>
          );
          return actionable ? (
            <button key={i} type="button" style={rowStyle} onClick={() => onNavigate(a.tab)}>
              {content}
            </button>
          ) : (
            <div key={i} style={rowStyle}>{content}</div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
