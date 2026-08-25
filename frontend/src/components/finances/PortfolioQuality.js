import React, { useCallback, useEffect, useState } from 'react';
import { getPortfolioQuality } from '../../api/investments';

const CLASS_LABEL = { equity: 'Equity', bond: 'Bonds', cash: 'Cash' };
const CLASS_COLOR = { equity: '#6366f1', bond: '#0ea5e9', cash: '#10b981' };

// One class: actual bar against a target marker. A bar plus a tick reads as
// "here vs there" without needing a legend.
function DriftBar({ row }) {
  const width = Math.min(row.actual, 100);
  return (
    <div style={{ display: 'grid', gap: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
        <span>{CLASS_LABEL[row.class] || row.class}</span>
        <span style={{ fontFamily: "'DM Mono', monospace", color: 'var(--text-muted)' }}>
          {row.actual}% <span aria-hidden="true">·</span> target {row.target}%
        </span>
      </div>
      <div style={{ position: 'relative', height: 10, borderRadius: 5, background: 'var(--border, #334155)' }}>
        <div style={{
          width: `${width}%`, height: '100%', borderRadius: 5,
          background: CLASS_COLOR[row.class] || '#94a3b8',
        }}
        />
        <div
          title={`Target ${row.target}%`}
          style={{
            position: 'absolute', top: -3, bottom: -3, left: `${Math.min(row.target, 100)}%`,
            width: 2, background: 'var(--text, #e2e8f0)',
          }}
        />
      </div>
    </div>
  );
}

/**
 * Portfolio quality — how concentrated the portfolio is, how far the mix sits
 * from the household's own stated risk band, and how much is idle cash.
 *
 * It deliberately stops there. Suggesting a rebalancing trade would be advice,
 * and the app cannot see the tax consequences of selling anything.
 */
export default function PortfolioQuality({ refreshKey = 0 }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    getPortfolioQuality()
      .then((r) => { setData(r.data); setFailed(false); })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  if (failed || !data || !data.available) return null;

  const { concentration: conc, allocation: alloc } = data;
  const concentrated = conc.flag === 'concentrated';

  return (
    <div className="finances-section">
      <h3 className="finances-section-title" style={{ marginTop: 0 }}>Portfolio quality</h3>

      <div style={{ display: 'grid', gap: 6, marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: concentrated ? '#f59e0b' : '#059669', fontWeight: 600 }}>
          {concentrated
            ? `Concentrated — ${conc.positions_over_threshold} position${conc.positions_over_threshold === 1 ? '' : 's'} above ${conc.threshold_pct}% of the portfolio`
            : `No single company above ${conc.threshold_pct}% of the portfolio`}
        </div>
        {concentrated && (
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {conc.positions_over.map((p) => `${p.symbol} ${p.pct}%`).join(' · ')}
          </div>
        )}
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Top 5 holdings are {conc.top_5_pct}% of the portfolio. The {conc.threshold_pct}% rule
          counts individual companies only — a broad fund at 20% is a diversified 20%.
        </div>
      </div>

      {alloc.drift ? (
        <div style={{ display: 'grid', gap: 10 }}>
          {alloc.drift.map((row) => <DriftBar key={row.class} row={row} />)}
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Target is the house mix for a{' '}
            <strong>{alloc.target_source.replace('risk_tolerance:', '')}</strong> risk tolerance.
            {alloc.largest_drift
              ? ` Furthest off: ${CLASS_LABEL[alloc.largest_drift.class] || alloc.largest_drift.class}, ${alloc.largest_drift.drift_pts} points from target.`
              : ''}
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Set a risk tolerance in settings and this will show your mix against a target.
        </div>
      )}

      <div style={{ marginTop: 14, display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-muted)' }}>
        <div>{data.cash_drag_pct}% of the portfolio is sitting in cash.</div>
        {alloc.etf_caveat && <div>{alloc.etf_caveat}</div>}
        <div>No trade suggestions here — we can&apos;t see your tax situation.</div>
      </div>
    </div>
  );
}
