import React from 'react';

export default function StatCard({ label, value, accent }) {
  return (
    <div className="stat-card">
      <div className="stat-val" style={{ color: accent || 'var(--text-primary)' }}>{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
