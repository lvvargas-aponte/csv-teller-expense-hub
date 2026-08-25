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
        <h2 className="finances-section-title" style={{ margin: 0 }}>{title}</h2>
        {headerExtra && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {headerExtra}
          </div>
        )}
      </div>
      <div className="eh-dcard-body">
        {loading && (
          <div className="eh-dcard-state"><Spin /> Loading…</div>
        )}
        {error && !loading && (
          <div className="eh-dcard-state eh-dcard-state--error">{error}</div>
        )}
        {empty && !loading && !error && (
          <div className="eh-dcard-state eh-dcard-state--empty">
            {emptyText || 'No data yet.'}
          </div>
        )}
        {!loading && !error && !empty && children}
      </div>
    </div>
  );
}