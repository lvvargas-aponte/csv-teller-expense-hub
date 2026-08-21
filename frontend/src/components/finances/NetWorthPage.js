import React, { useMemo } from 'react';
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import Spin from '../ui/Spin';
import { fmt$, fmtSigned, formatRelativeTime } from '../../utils/formatting';

const AXIS = { fontSize: 11, fill: 'var(--text-secondary, #94a3b8)' };

/**
 * NetWorthPage — the one place the household's net worth is stated.
 *
 * It used to be a banner buried at the bottom of Accounts, competing with a
 * right-rail card on the same screen that computed cash − owed and called that
 * net worth too. That rail figure subtracted mortgages (they arrive from the
 * bank as `credit` accounts) while counting neither investments nor the houses
 * securing them, so it read far below the real position.
 *
 * The number here is ``summary.net_worth`` — the server's, computed once — and
 * the rows below it are the terms of that same sum, so the breakdown reconciles
 * exactly rather than being an independent re-derivation:
 *
 *   net worth = cash + investments + property value
 *               − credit debt − unlinked property debt
 *
 * The last term is the subtle one. A mortgage that syncs from the bank is
 * already inside `total_credit_debt`; only hand-entered loans backed by no
 * account still need subtracting. Adding `total_property_debt` here instead
 * would subtract the synced mortgage twice.
 */
export default function NetWorthPage({ summary, loading, error, dashboard, onRefresh }) {
  const rows = useMemo(() => {
    if (!summary) return null;

    const cash        = summary.total_cash ?? 0;
    const investments = summary.total_investments ?? 0;
    const propValue   = summary.total_property_value ?? 0;
    const creditDebt  = summary.total_credit_debt ?? 0;
    const propDebt    = summary.total_property_debt ?? 0;
    const linkedDebt  = summary.total_property_debt_linked ?? 0;
    const unlinkedDebt = summary.total_property_debt_unlinked ?? 0;

    const assets = [
      { key: 'cash',        icon: '🏦', label: 'Cash & Savings',   value: cash },
      { key: 'investments', icon: '📈', label: 'Investments & Retirement', value: investments },
      { key: 'property',    icon: '🏠', label: 'Property value',   value: propValue },
    ].filter((r) => r.value !== 0);

    const liabilities = [
      {
        key: 'credit',
        icon: '💳',
        label: 'Credit cards & loans',
        value: creditDebt,
        note: linkedDebt > 0
          ? `includes ${fmt$(linkedDebt)} of mortgage balances that sync as accounts`
          : null,
      },
      {
        key: 'property-debt',
        icon: '🏛️',
        label: 'Other property debt',
        value: unlinkedDebt,
        note: 'hand-entered loans that sync from no account',
      },
    ].filter((r) => r.value !== 0);

    const totalAssets      = assets.reduce((s, r) => s + r.value, 0);
    const totalLiabilities = liabilities.reduce((s, r) => s + r.value, 0);

    return {
      assets,
      liabilities,
      totalAssets,
      totalLiabilities,
      propValue,
      propDebt,
      propEquity: summary.total_property_equity ?? 0,
      // The server's figure is authoritative; this is only used to notice if
      // the two ever disagree (a new asset class landing in net_worth without
      // a row here would show up as a gap rather than silently hiding).
      derived: totalAssets - totalLiabilities,
    };
  }, [summary]);

  const netWorth = summary?.net_worth ?? 0;
  const series = dashboard?.net_worth_timeseries || [];
  const trend = dashboard?.balance_trend;
  const drift = rows ? Math.abs(rows.derived - netWorth) : 0;

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="ov-card">
        <div className="ov-nw-banner">
          <div className="ov-nw-left">
            <div className="ov-nw-label">Net Worth</div>
            <div className={`ov-nw-value${netWorth < 0 ? ' ov-nw-value--neg' : ''}`}>
              {loading && !summary ? '—' : fmtSigned(netWorth)}
            </div>
            <div className="ov-nw-sub">
              <span>Everything you own, minus everything you owe</span>
            </div>
            {summary?.cache_fetched_at && (
              <div className="ov-nw-updated">
                Updated {formatRelativeTime(summary.cache_fetched_at)}
              </div>
            )}
          </div>
          <div className="ov-nw-actions">
            {trend?.available && (trend.delta_30d !== null && trend.delta_30d !== undefined) && (
              <div className="nw-delta">
                <div className="nw-delta-label">30-day change</div>
                <div className="nw-delta-value">
                  {trend.delta_30d >= 0 ? '+' : ''}{fmt$(Math.abs(trend.delta_30d))}
                </div>
              </div>
            )}
            <button
              type="button"
              className="ov-nw-btn"
              onClick={onRefresh}
              disabled={loading}
              title="Fetch latest balances"
            >
              {loading ? <><Spin /> Refreshing…</> : '↺ Refresh'}
            </button>
          </div>
        </div>

        <div className="ov-card-body">
          {loading && !summary && (
            <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-muted)' }}>
              <Spin /> Loading…
            </div>
          )}
          {error && <div className="ov-error">{error}</div>}

          {!error && rows && (
            <div className="nw-breakdown">
              <NetWorthGroup
                title="Assets"
                rows={rows.assets}
                total={rows.totalAssets}
                tone="pos"
                emptyText="No assets recorded yet."
              />
              <NetWorthGroup
                title="Liabilities"
                rows={rows.liabilities}
                total={rows.totalLiabilities}
                tone="neg"
                sign="−"
                emptyText="No debt recorded — nothing to subtract."
              />

              <div className="nw-total-row">
                <span className="nw-total-label">Net worth</span>
                <span className={`nw-total-value${netWorth < 0 ? ' is-neg' : ''}`}>
                  {fmtSigned(netWorth)}
                </span>
              </div>

              {drift >= 0.02 && (
                <div className="nw-drift-note">
                  Heads up: these rows total {fmtSigned(rows.derived)}, which doesn&apos;t
                  match the reported net worth of {fmtSigned(netWorth)}. Something is
                  counted in the total that isn&apos;t itemised above.
                </div>
              )}

              {rows.propValue > 0 && (
                <div className="nw-equity-note">
                  <strong>Property equity: {fmt$(rows.propEquity)}</strong>
                  <div>
                    {fmt$(rows.propValue)} of property value less {fmt$(rows.propDebt)} still
                    owed on it. That equity is part of the net worth above — mortgages are
                    subtracted, and the homes they secure are counted.
                  </div>
                </div>
              )}

              {summary?.unvalued_properties?.length > 0 && (
                <div className="nw-warning-note">
                  Not counted: {summary.unvalued_properties.join(', ')} — no valuation on
                  file. Add an estimated value on the Properties page and it&apos;ll be
                  included here.
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {series.length > 0 && (
        <div className="finances-section">
          <h2 className="finances-section-title">Trend</h2>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={series}>
              <defs>
                <linearGradient id="nw-page-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgba(5,150,105,0.18)" />
                  <stop offset="100%" stopColor="rgba(5,150,105,0.02)" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #d1fae5)" />
              <XAxis dataKey="date" tick={AXIS} minTickGap={30} />
              <YAxis tick={AXIS} tickFormatter={(v) => fmt$(v)} width={70} />
              <Tooltip formatter={(v) => fmtSigned(v)} />
              <Area type="monotone" dataKey="net_worth"
                    stroke="#059669" strokeWidth={2.5}
                    fill="url(#nw-page-fill)" />
            </AreaChart>
          </ResponsiveContainer>
          <div className="nw-trend-note">
            Built from balance snapshots, so it starts when your history does.
          </div>
        </div>
      )}
    </div>
  );
}

function NetWorthGroup({ title, rows, total, tone, sign = '', emptyText }) {
  return (
    <div className="nw-group">
      <div className="nw-group-head">
        <span className="nw-group-title">{title}</span>
        <span className={`nw-group-total is-${tone}`}>{sign}{fmt$(total)}</span>
      </div>
      {rows.length === 0 ? (
        <div className="nw-group-empty">{emptyText}</div>
      ) : rows.map((r) => (
        <div key={r.key} className="nw-row">
          <span className="nw-row-icon" aria-hidden="true">{r.icon}</span>
          <span className="nw-row-label">
            {r.label}
            {r.note && <span className="nw-row-note">{r.note}</span>}
          </span>
          <span className={`nw-row-value is-${tone}`}>{sign}{fmt$(r.value)}</span>
        </div>
      ))}
    </div>
  );
}
