import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import { fmt$ } from '../../../utils/formatting';

const PALETTE = [
  'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)',
  'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)',
];
const TOP_N = 8;
const AXIS = { fontSize: 11, fill: 'var(--text-faint)' };
const HIDDEN_KEY = 'dashboard.spendByCat.hidden';

const loadHidden = () => {
  try {
    const raw = localStorage.getItem(HIDDEN_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
};

export default function SpendingByCategoryCard({ dashboard, loading, error, onHide, index, kicker }) {
  const [hidden, setHidden] = useState(loadHidden);

  useEffect(() => {
    try {
      localStorage.setItem(HIDDEN_KEY, JSON.stringify([...hidden]));
    } catch { /* ignore quota / privacy errors */ }
  }, [hidden]);

  const toggleHidden = (cat) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat); else next.add(cat);
      return next;
    });
  };
  const clearHidden = () => setHidden(new Set());

  const { rows, keys, allRanked } = useMemo(() => {
    const months = dashboard?.months || [];
    const spendingByMonth = dashboard?.spending_by_month || {};
    if (!months.length) return { rows: [], keys: [], allRanked: [] };
    const totals = {};
    months.forEach((m) => {
      Object.entries(spendingByMonth[m] || {}).forEach(([cat, val]) => {
        totals[cat] = (totals[cat] || 0) + val;
      });
    });
    const ranked = Object.entries(totals).sort((a, b) => b[1] - a[1]);
    const kept = ranked.filter(([c]) => !hidden.has(c));
    const top = kept.slice(0, TOP_N).map(([c]) => c);
    const hasOther = kept.length > TOP_N;
    const builtRows = months.map((m) => {
      const row = { month: m };
      let other = 0;
      Object.entries(spendingByMonth[m] || {}).forEach(([cat, val]) => {
        if (hidden.has(cat)) return;
        if (top.includes(cat)) row[cat] = val;
        else other += val;
      });
      if (hasOther) row.Other = +other.toFixed(2);
      return row;
    });
    return {
      rows: builtRows,
      keys: hasOther ? [...top, 'Other'] : top,
      allRanked: ranked,
    };
  }, [dashboard, hidden]);

  const empty = !loading && !error && rows.length === 0;
  const hiddenCount = allRanked.filter(([c]) => hidden.has(c)).length;

  const filterControl = allRanked.length > 0 ? (
    <details className="eh-dcard-filter">
      <summary
        className="eh-dcard-filter-btn"
        title="Hide categories from this chart"
      >
        Filter{hiddenCount > 0 ? ` · ${hiddenCount}` : ''} ▾
      </summary>
      <div className="eh-dcard-filter-menu" role="menu">
        <div className="eh-dcard-filter-head">
          <span>Show categories</span>
          {hiddenCount > 0 && (
            <button
              type="button"
              className="eh-dcard-filter-clear"
              onClick={clearHidden}
            >
              Reset
            </button>
          )}
        </div>
        <ul className="eh-dcard-filter-list">
          {allRanked.map(([cat, total]) => {
            const id = `spendcat-${cat}`;
            const checked = !hidden.has(cat);
            return (
              <li key={cat}>
                <label htmlFor={id} className="eh-dcard-filter-item">
                  <input
                    id={id}
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleHidden(cat)}
                  />
                  <span className="eh-dcard-filter-name">{cat}</span>
                  <span className="eh-dcard-filter-amt">{fmt$(total)}</span>
                </label>
              </li>
            );
          })}
        </ul>
      </div>
    </details>
  ) : null;

  return (
    <DashboardCard
      title="Spending by Category"
      index={index}
      kicker={kicker}
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No spending in this window."
      onHide={onHide}
      headerExtra={filterControl}
    >
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
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