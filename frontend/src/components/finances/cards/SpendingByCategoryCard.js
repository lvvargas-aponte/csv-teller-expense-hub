import React, { useMemo } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import { fmt$ } from '../../../utils/formatting';

const PALETTE = [
  '#059669', '#6366f1', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16',
  '#94a3b8',
];
const TOP_N = 8;
const AXIS = { fontSize: 11, fill: 'var(--text-secondary, #94a3b8)' };

export default function SpendingByCategoryCard({ dashboard, loading, error, onHide }) {
  const { rows, keys } = useMemo(() => {
    const months = dashboard?.months || [];
    const spendingByMonth = dashboard?.spending_by_month || {};
    if (!months.length) return { rows: [], keys: [] };
    const totals = {};
    months.forEach((m) => {
      Object.entries(spendingByMonth[m] || {}).forEach(([cat, val]) => {
        totals[cat] = (totals[cat] || 0) + val;
      });
    });
    const ranked = Object.entries(totals).sort((a, b) => b[1] - a[1]);
    const top = ranked.slice(0, TOP_N).map(([c]) => c);
    const hasOther = ranked.length > TOP_N;
    const builtRows = months.map((m) => {
      const row = { month: m };
      let other = 0;
      Object.entries(spendingByMonth[m] || {}).forEach(([cat, val]) => {
        if (top.includes(cat)) row[cat] = val;
        else other += val;
      });
      if (hasOther) row.Other = +other.toFixed(2);
      return row;
    });
    return { rows: builtRows, keys: hasOther ? [...top, 'Other'] : top };
  }, [dashboard]);

  const empty = !loading && !error && rows.length === 0;

  return (
    <DashboardCard
      title="Spending by Category"
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No spending in this window."
      onHide={onHide}
    >
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #334155)" />
          <XAxis dataKey="month" tick={AXIS} />
          <YAxis tick={AXIS} tickFormatter={(v) => fmt$(v)} width={70} />
          <Tooltip formatter={(v) => fmt$(v)} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {keys.map((cat, i) => (
            <Bar key={cat} dataKey={cat} stackId="spend" fill={PALETTE[i % PALETTE.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </DashboardCard>
  );
}
