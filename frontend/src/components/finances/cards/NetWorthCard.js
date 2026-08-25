import React from 'react';
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import { fmt$, fmtSigned } from '../../../utils/formatting';
import Num from '../Num';
import { liquidLabel, netWorthComposition } from '../../../utils/netWorth';

const AXIS = { fontSize: 11, fill: 'var(--text-secondary, #94a3b8)' };

export default function NetWorthCard({
  dashboard, summary, loading, error, onHide, index, kicker,
}) {
  const trend = dashboard?.balance_trend;
  const series = dashboard?.net_worth_timeseries || [];
  const empty = !loading && !error && series.length === 0 && !trend?.available;
  const parts = netWorthComposition(summary);
  // Illiquid value inflates net worth without improving resilience, so the two
  // figures sit side by side rather than one standing in for the other.
  const liquid = liquidLabel(summary, trend?.current_net_worth ?? null);

  return (
    <DashboardCard
      title="Net Worth"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No balance snapshots yet — sync or add a manual balance."
      onHide={onHide}
    >
      {trend?.available && (
        <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 13, flexWrap: 'wrap' }}>
          <div>
            <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>Current</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>
              <Num value={trend.current_net_worth} signed />
            </div>
          </div>
          {liquid !== null && (
            <div>
              <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                Liquid
                <span className="eh-info-wrap" tabIndex={0} aria-label="About liquid net worth">
                  <span className="eh-info-icon">i</span>
                  <span className="eh-info-tooltip" role="tooltip">
                    <div className="eh-info-tooltip-title">Liquid net worth</div>
                    Everything except property and vehicles. A house raises net
                    worth without making a hard month any easier, so the
                    emergency-fund runway ignores it on purpose — this is the
                    figure that ratio reasons about.
                  </span>
                </span>
              </div>
              <div style={{ fontSize: 18, fontWeight: 700 }}>{liquid}</div>
            </div>
          )}
          {(trend.delta_30d !== null && trend.delta_30d !== undefined) && (
            <div>
              <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>30-day Δ</div>
              <div style={{
                fontSize: 18, fontWeight: 700,
                color: trend.delta_30d >= 0 ? '#059669' : '#ef4444',
              }}>
                <Num value={trend.delta_30d} signed prefix={trend.delta_30d >= 0 ? '+' : ''} />
              </div>
            </div>
          )}
          {trend.label && (
            <div>
              <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>Trend</div>
              <div style={{ fontSize: 14, fontWeight: 600, textTransform: 'capitalize' }}>
                {trend.label}
              </div>
            </div>
          )}
        </div>
      )}
      {parts && (
        <div
          className="nw-composition"
          role="group"
          aria-label="What makes up net worth"
        >
          {parts.map((p) => (
            <div key={p.key} className="nw-part">
              <span className="nw-part-label">{p.label}</span>
              <span className={`nw-part-value${p.value < 0 ? ' is-neg' : ''}`}>
                {fmtSigned(p.value)}
              </span>
            </div>
          ))}
        </div>
      )}
      {series.length > 0 && (
        <ResponsiveContainer width="100%" height={160}>
          <AreaChart data={series}>
            <defs>
              <linearGradient id="nw-fill" x1="0" y1="0" x2="0" y2="1">
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
                  fill="url(#nw-fill)" />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </DashboardCard>
  );
}
