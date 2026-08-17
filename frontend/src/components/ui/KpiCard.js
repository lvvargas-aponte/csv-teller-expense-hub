import React from 'react';

import { fmt$ } from '../../utils/formatting';

/**
 * A single KPI tile: label (+ optional info tooltip), a large mono value,
 * an optional signed delta, and a colored accent bar.
 *
 * Extracted from DashboardTab so the Today, Properties, and Retirement pages
 * can reuse it rather than restating the markup.
 *
 * @param label        Tile heading, e.g. "Net Worth".
 * @param value        Preformatted display string — callers pick fmt$ vs fmtSigned.
 * @param valueClass   Extra class for the value, e.g. 'eh-kpi-value--neg'.
 * @param delta        Raw number compared with the prior period; null hides the row.
 * @param deltaInverse Set when a DROP is good (spending), so the color flips.
 * @param barColor     Accent strip color.
 * @param blur         Applies the privacy blur used by the "Hide numbers" toggle.
 * @param help         Tooltip body; omitted renders no info icon.
 * @param sub          Static qualifier under the value, e.g. "65.03% LTV".
 *                     Unlike `delta` it is not compared with a prior period
 *                     and takes no sign coloring; omitted renders nothing.
 */
export default function KpiCard({
  label,
  value,
  valueClass,
  delta,
  deltaInverse,
  barColor,
  blur,
  help,
  sub,
}) {
  const hasDelta = delta !== null && delta !== undefined;

  let arrow = null;
  let deltaColor = 'var(--text-muted)';
  if (hasDelta) {
    const positive = delta >= 0;
    arrow = positive ? '↑' : '↓';
    const good = deltaInverse ? !positive : positive;
    deltaColor = good ? '#059669' : '#ef4444';
  }

  return (
    <div className="eh-kpi">
      <div className="eh-kpi-label">
        <span>{label}</span>
        {help && (
          <span className="eh-info-wrap eh-kpi-info" tabIndex={0} aria-label={`About ${label}`}>
            <span className="eh-info-icon">i</span>
            <span className="eh-info-tooltip" role="tooltip">
              <div className="eh-info-tooltip-title">{label}</div>
              {help}
            </span>
          </span>
        )}
      </div>
      <div className={`eh-kpi-value ${valueClass || ''}${blur ? ' eh-blur' : ''}`}>{value}</div>
      {sub && (
        <div className={`eh-kpi-sub${blur ? ' eh-blur' : ''}`}>{sub}</div>
      )}
      {hasDelta && (
        <div className="eh-kpi-delta" style={{ color: deltaColor }}>
          <span>{arrow}</span>
          <span className={blur ? 'eh-blur' : ''}>{fmt$(delta)}</span>
          <span className="eh-kpi-delta-suffix">vs prior</span>
        </div>
      )}
      <div className="eh-kpi-bar" style={{ background: barColor }} />
    </div>
  );
}
