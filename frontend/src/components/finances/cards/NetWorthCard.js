import React from 'react';
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import { fmt$, fmtSigned } from '../../../utils/formatting';

const AXIS = { fontSize: 11, fill: 'var(--text-secondary, #94a3b8)' };

export default function NetWorthCard({ dashboard, loading, error, onHide }) {
  const trend = dashboard?.balance_trend;
  const series = dashboard?.net_worth_timeseries || [];
  const empty = !loading && !error && series.length === 0 && !trend?.available;

  return (
    <DashboardCard
      title="Net Worth"
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
              {fmtSigned(trend.current_net_worth)}
            </div>
          </div>
          {trend.delta_30d != null && (
            <div>
              <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>30-day Δ</div>
              <div style={{
                fontSize: 18, fontWeight: 700,
                color: trend.delta_30d >= 0 ? '#059669' : '#ef4444',
              }}>
                {trend.delta_30d >= 0 ? '+' : ''}{fmtSigned(trend.delta_30d)}
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
