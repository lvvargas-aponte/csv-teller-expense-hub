import React from 'react';
import Spin from '../../ui/Spin';

export default function DashboardCard({
  title,
  loading,
  error,
  empty,
  emptyText,
  children,
  headerExtra,
}) {
  return (
    <div className="finances-section dashboard-card">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          userSelect: 'none',
          marginBottom: 8,
        }}
      >
        <h3 className="finances-section-title" style={{ margin: 0 }}>{title}</h3>
        {headerExtra && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {headerExtra}
          </div>
        )}
      </div>
      <div>
        {loading && (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <Spin /> Loading…
          </div>
        )}
        {error && !loading && (
          <div style={{ color: '#ef4444', fontSize: 13 }}>{error}</div>
        )}
        {empty && !loading && !error && (
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            {emptyText || 'No data yet.'}
          </div>
        )}
        {!loading && !error && !empty && children}
      </div>
    </div>
  );
}
