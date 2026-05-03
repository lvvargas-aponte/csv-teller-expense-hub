import React, { useEffect, useState } from 'react';
import DashboardCard from './DashboardCard';
import { getAlerts } from '../../../api/dashboard';

const SEVERITY = {
  error: { color: '#ef4444', icon: '!' },
  warn:  { color: '#f59e0b', icon: '⚠' },
  info:  { color: '#059669', icon: 'i' },
};

export default function AlertsCard({ onHide }) {
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
      loading={loading}
      error={error}
      empty={empty}
      emptyText="All clear — no alerts."
      onHide={onHide}
    >
      <div style={{ display: 'grid', gap: 6 }}>
        {alerts.map((a, i) => {
          const sev = SEVERITY[a.severity] || SEVERITY.info;
          return (
            <div
              key={i}
              style={{
                display: 'flex',
                gap: 8,
                padding: '6px 8px',
                borderLeft: `3px solid ${sev.color}`,
                background: 'rgba(255,255,255,0.02)',
                fontSize: 13,
              }}
            >
              <span style={{ color: sev.color, fontWeight: 700 }}>{sev.icon}</span>
              <span>{a.message}</span>
            </div>
          );
        })}
      </div>
    </DashboardCard>
  );
}
