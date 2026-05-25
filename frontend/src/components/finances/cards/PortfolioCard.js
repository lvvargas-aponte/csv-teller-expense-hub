import React, { useEffect, useState } from 'react';
import {
  Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import Num from '../Num';
import { fmt$ } from '../../../utils/formatting';
import { getPortfolio } from '../../../api/investments';

// Stable colors per asset class so the allocation strip & bars match.
const ALLOC_COLORS = {
  stock: '#6366f1',
  etf: '#0ea5e9',
  crypto: '#f59e0b',
  option: '#a855f7',
  cash: '#10b981',
  other: '#94a3b8',
};

const ASSET_LABEL = {
  stock: 'Stocks',
  etf: 'ETFs',
  crypto: 'Crypto',
  option: 'Options',
  cash: 'Cash',
  other: 'Other',
};

const UNREALIZED_HELP =
  "Unrealized P/L is the paper gain or loss on holdings you still own: " +
  "current market value minus what you paid (cost basis). It becomes 'realized' only when you sell.";

const AXIS = { fontSize: 11, fill: 'var(--text-secondary, #94a3b8)' };

export default function PortfolioCard({ onHide, index, kicker }) {
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getPortfolio()
      .then((r) => setPortfolio(r.data))
      .catch(() => setError('Could not load portfolio.'))
      .finally(() => setLoading(false));
  }, []);

  const empty = !loading && !error && (!portfolio || portfolio.holding_count === 0);
  const gain = portfolio?.total_gain ?? 0;
  const gainColor = gain >= 0 ? '#059669' : '#ef4444';
  const gainPct = portfolio?.total_gain_pct;
  const allocation = portfolio?.allocation || [];

  // Top 6 holdings shaped for the bar chart, colored by asset_type.
  const barData = (portfolio?.concentration || []).slice(0, 6).map((h) => {
    const full = (portfolio.holdings || []).find((x) => x.symbol === h.symbol);
    return {
      symbol: h.symbol,
      value: h.value,
      pct: h.pct,
      asset_type: full?.asset_type || 'other',
    };
  });

  return (
    <DashboardCard
      title="Investment Portfolio"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No holdings yet — connect a brokerage on the Investments tab."
      onHide={onHide}
    >
      {portfolio && (
        <>
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Portfolio Value</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>
              <Num value={portfolio.total_value} />
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              <span title={UNREALIZED_HELP} style={{ cursor: 'help', borderBottom: '1px dotted var(--text-muted)' }}>
                Unrealized
              </span>{' '}
              <span style={{ color: gainColor, fontWeight: 600 }}>
                <Num value={gain} signed prefix={gain >= 0 ? '+' : ''} />
                {gainPct !== null && gainPct !== undefined &&
                  ` (${gainPct >= 0 ? '+' : ''}${gainPct}%)`}
              </span>
              {' · '}{portfolio.holding_count} position{portfolio.holding_count === 1 ? '' : 's'}
            </div>
          </div>

          {allocation.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', marginBottom: 6 }}>
                {allocation.map((a) => (
                  <div
                    key={a.asset_type}
                    title={`${ASSET_LABEL[a.asset_type] || a.asset_type}: ${a.pct}%`}
                    style={{ width: `${a.pct}%`, background: ALLOC_COLORS[a.asset_type] || ALLOC_COLORS.other }}
                  />
                ))}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, fontSize: 11, color: 'var(--text-muted)' }}>
                {allocation.map((a) => (
                  <span key={a.asset_type} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: 2,
                      background: ALLOC_COLORS[a.asset_type] || ALLOC_COLORS.other,
                    }} />
                    {ASSET_LABEL[a.asset_type] || a.asset_type} {a.pct}%
                  </span>
                ))}
              </div>
            </div>
          )}

          {barData.length > 0 && (
            <>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                Top positions by market value
              </div>
              <ResponsiveContainer width="100%" height={Math.max(120, barData.length * 28)}>
                <BarChart data={barData} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }}>
                  <XAxis type="number" tick={AXIS} tickFormatter={(v) => fmt$(v)} />
                  <YAxis type="category" dataKey="symbol" tick={AXIS} width={64} />
                  <Tooltip
                    formatter={(v, _n, p) => [`${fmt$(v)} (${p.payload.pct}%)`, p.payload.symbol]}
                    labelFormatter={() => ''}
                  />
                  <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                    {barData.map((d) => (
                      <Cell key={d.symbol} fill={ALLOC_COLORS[d.asset_type] || ALLOC_COLORS.other} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </>
          )}
        </>
      )}
    </DashboardCard>
  );
}