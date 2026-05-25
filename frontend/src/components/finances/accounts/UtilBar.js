import React from 'react';

// Color thresholds match the design handoff: <30% green, 30-70% amber, >70% red.
export function utilColor(pct) {
  if ((pct === null || pct === undefined)) return null;
  if (pct > 70) return 'var(--red)';
  if (pct >= 30) return 'var(--amber)';
  return 'var(--accent)';
}

// Renders a thin progress bar with a right-aligned percent label. When pct is
// null (e.g. no credit limit set) returns null so callers don't have to guard.
export default function UtilBar({ pct, showLabel = true }) {
  if ((pct === null || pct === undefined)) return null;
  const clamped = Math.max(0, Math.min(100, pct));
  const color = utilColor(pct);
  return (
    <div className="util-bar">
      <div className="util-bar-track">
        <div
          className="util-bar-fill"
          style={{ width: `${clamped}%`, background: color }}
        />
      </div>
      {showLabel && (
        <span className="util-bar-label" style={{ color }}>
          {Math.round(pct)}%
        </span>
      )}
    </div>
  );
}
