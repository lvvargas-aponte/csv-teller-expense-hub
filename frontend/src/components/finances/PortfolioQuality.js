import React, { useCallback, useEffect, useState } from 'react';
import { fmt$ } from '../../utils/formatting';
import { getPortfolioQuality, getPortfolioFees, getMixBacktest } from '../../api/investments';

const CLASS_LABEL = { equity: 'Equity', bond: 'Bonds', cash: 'Cash' };
const CLASS_COLOR = { equity: 'var(--chart-1)', bond: 'var(--chart-4)', cash: 'var(--chart-6)' };
const PERIOD_LABEL = { '1mo': 'Past month', '1y': 'Past year', '5y': 'Past 5 years' };

// Fees are decided in dollars, not basis points — cents on an annual estimate
// are noise, so the headline figure is whole dollars.
const fmtWhole = (n) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
}).format(Math.abs(parseFloat(n) || 0));

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
      <div style={{ position: 'relative', height: 10, borderRadius: 5, background: 'var(--border)' }}>
        <div style={{
          width: `${width}%`, height: '100%', borderRadius: 5,
          background: CLASS_COLOR[row.class] || 'var(--text-faint)',
        }}
        />
        <div
          title={`Target ${row.target}%`}
          style={{
            position: 'absolute', top: -3, bottom: -3, left: `${Math.min(row.target, 100)}%`,
            width: 2, background: 'var(--text)',
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
  const [fees, setFees] = useState(null);
  const [backtest, setBacktest] = useState(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    getPortfolioQuality()
      .then((r) => { setData(r.data); setFailed(false); })
      .catch(() => setFailed(true));
    // Both of these reach the network. Neither is allowed to take the card
    // down with it — an offline install still sees concentration and drift.
    getPortfolioFees().then((r) => setFees(r.data)).catch(() => setFees(null));
    getMixBacktest().then((r) => setBacktest(r.data)).catch(() => setBacktest(null));
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);

  if (failed || !data || !data.available) return null;

  const { concentration: conc, allocation: alloc } = data;
  const concentrated = conc.flag === 'concentrated';
  const expensive = (fees?.holdings || []).filter((f) => f.high);

  return (
    <div className="finances-section">
      <h2 className="finances-section-title" style={{ marginTop: 0 }}>Portfolio quality</h2>

      <div style={{ display: 'grid', gap: 6, marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: concentrated ? 'var(--status-warn-text)' : 'var(--status-good-text)', fontWeight: 600 }}>
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

      {fees && fees.available && (
        <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
          <div style={{ fontSize: 18, fontWeight: 700 }}>
            {fmtWhole(fees.annual_fee_cost)}/year in fund fees
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
            {fees.weighted_expense_ratio_pct}% weighted across {fmt$(fees.fund_value)} in{' '}
            {fees.funds_priced} fund{fees.funds_priced === 1 ? '' : 's'}.
          </div>
          {expensive.length > 0 && (
            <div style={{ marginTop: 8, display: 'grid', gap: 3, fontSize: 12 }}>
              <div style={{ color: 'var(--status-warn-text)' }}>
                Above {fees.high_fee_threshold_pct}%:
              </div>
              {expensive.map((f) => (
                <div key={f.symbol} style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{f.symbol}</span>
                  <span style={{ fontFamily: "'DM Mono', monospace" }}>
                    {fmtWhole(f.annual_cost)}/yr <span style={{ color: 'var(--text-muted)' }}>({f.expense_ratio_pct}%)</span>
                  </span>
                </div>
              ))}
            </div>
          )}
          {fees.unpriced_symbols.length > 0 && (
            <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
              Not in the average — no published expense ratio:{' '}
              {fees.unpriced_symbols.join(', ')}.
            </div>
          )}
        </div>
      )}

      {backtest && backtest.available && (
        <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            How your current mix would have performed
          </div>
          <div style={{ marginTop: 8, display: 'grid', gap: 4, fontSize: 12 }}>
            {Object.values(backtest.periods).map((p) => (
              <div key={p.period} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <span style={{ color: 'var(--text-muted)' }}>{PERIOD_LABEL[p.period] || p.period}</span>
                {p.available ? (
                  <span style={{ fontFamily: "'DM Mono', monospace" }}>
                    <span style={{ color: p.mix_return_pct >= 0 ? 'var(--status-good-text)' : 'var(--status-bad-text)' }}>
                      {p.mix_return_pct >= 0 ? '+' : ''}{p.mix_return_pct}%
                    </span>
                    {p.benchmark_return_pct !== null && p.benchmark_return_pct !== undefined && (
                      <span style={{ color: 'var(--text-muted)' }}>
                        {' '}vs {p.benchmark} {p.benchmark_return_pct >= 0 ? '+' : ''}{p.benchmark_return_pct}%
                      </span>
                    )}
                  </span>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>{p.reason}</span>
                )}
              </div>
            ))}
          </div>
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-muted)' }}>
            {backtest.disclaimer}
            {backtest.unpriceable_symbols.length > 0
              ? ` Couldn't price: ${backtest.unpriceable_symbols.join(', ')}.`
              : ''}
          </div>
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
