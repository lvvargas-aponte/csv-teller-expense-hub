import React from 'react';
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import { fmt$ } from '../../../utils/formatting';

const AXIS = { fontSize: 11, fill: 'var(--text-faint, #9ca3af)' };

export default function CashFlowCard({ dashboard, loading, error, onHide }) {
  const totals = dashboard?.monthly_totals || [];
  const empty = !loading && !error && totals.length === 0;

  const latest = totals[totals.length - 1]?.total ?? 0;
  const prev = totals[totals.length - 2]?.total ?? null;
  const delta = prev != null ? latest - prev : null;
  const high = latest >= 12000;

  return (
    <DashboardCard
      title="Monthly Spending"
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No spending in this window."
      onHide={onHide}
      headerExtra={
        <span style={{
          fontSize: 10, fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: '0.04em',
          padding: '2px 8px', borderRadius: 99,
          background: high ? '#fee2e2' : '#d1fae5',
          color: high ? '#ef4444' : '#059669',
        }}>
          {high ? 'High' : 'On track'}
        </span>
      }
    >
      <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 13 }}>
        <div>
          <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>This month</div>
          <div style={{ fontSize: 19, fontWeight: 700, fontFamily: "'DM Mono', monospace" }}>
            {fmt$(latest)}
          </div>
        </div>
        {delta != null && (
          <div>
            <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>vs. last</div>
            <div style={{
              fontSize: 19, fontWeight: 700,
              color: delta <= 0 ? '#059669' : '#ef4444',
              fontFamily: "'DM Mono', monospace",
            }}>
              {delta >= 0 ? '+' : '-'}{fmt$(delta)}
            </div>
          </div>
        )}
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <BarChart data={totals}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #d1fae5)" />
          <XAxis dataKey="month" tick={AXIS} />
          <YAxis tick={AXIS} tickFormatter={(v) => fmt$(v)} width={70} />
          <Tooltip formatter={(v) => fmt$(v)} />
          <Bar dataKey="total" fill="#6366f1" fillOpacity={0.8} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </DashboardCard>
  );
}
