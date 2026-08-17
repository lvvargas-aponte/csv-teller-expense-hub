import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import { fmt$ } from '../../../utils/formatting';

// Rank is carried by bar length, so the fill is one hue for every real category
// and a de-emphasis gray for the synthetic "Other" roll-up. Both steps clear 3:1
// against their card surface (#ffffff light, #0e2218 dark).
const BAR_FILL = 'var(--viz-bar, #059669)';
const BAR_FILL_OTHER = 'var(--viz-bar-muted, #6b7280)';

const TOP_N = 10;
const ROW_H = 30;          // per-bar row height; the chart grows with the data
const CHART_PAD = 44;      // axis + margins
const NAME_W = 150;        // category-label gutter — fits ~24ch before ellipsis
const AXIS = { fontSize: 11, fill: 'var(--text-muted, #6b7280)' };
const HIDDEN_KEY = 'dashboard.spendByCat.hidden';

const loadHidden = () => {
  try {
    const raw = localStorage.getItem(HIDDEN_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
};

// "2026-07" -> "Jul 2026". Falls back to the raw key if it isn't a month bucket.
const monthLabel = (key) => {
  const m = /^(\d{4})-(\d{2})$/.exec(key || '');
  if (!m) return key;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, 1);
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
};

const rangeLabel = (months) => {
  if (!months.length) return '';
  const first = monthLabel(months[0]);
  const last = monthLabel(months[months.length - 1]);
  return first === last ? first : `${first} – ${last}`;
};

// Axis ticks only need the order of magnitude — the exact figure rides on the bar.
const fmtTick = (v) => (v >= 1000 ? `$${Math.round(v / 1000)}k` : `$${v}`);

const truncate = (s, max = 24) => (s.length > max ? `${s.slice(0, max - 1)}…` : s);

// Recharts hands YAxis a plain tick payload; render it ourselves so long
// category names ellipsize inside the gutter instead of overflowing the card.
function CategoryTick({ x, y, payload }) {
  return (
    <text
      x={x}
      y={y}
      dy={4}
      textAnchor="end"
      fontSize={11}
      fill="var(--text-secondary, #374151)"
    >
      <title>{payload.value}</title>
      {truncate(payload.value)}
    </text>
  );
}

function SpendTooltip({ active, payload, monthCount }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="eh-viz-tooltip">
      <div className="eh-viz-tooltip-title">{row.category}</div>
      <div className="eh-viz-tooltip-row">
        <span>Total</span><strong>{fmt$(row.amount)}</strong>
      </div>
      <div className="eh-viz-tooltip-row">
        <span>Share</span><strong>{row.share.toFixed(1)}%</strong>
      </div>
      {monthCount > 1 && (
        <div className="eh-viz-tooltip-row">
          <span>Per month</span><strong>{fmt$(row.amount / monthCount)}</strong>
        </div>
      )}
    </div>
  );
}

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

  const { rows, total, allRanked, months } = useMemo(() => {
    const mos = dashboard?.months || [];
    const spendingByMonth = dashboard?.spending_by_month || {};
    if (!mos.length) return { rows: [], total: 0, allRanked: [], months: [] };

    // The card answers "where did the money go over this window", so totals are
    // summed across every month in it rather than split per month — with one
    // month loaded a per-month stack collapses into a single unreadable column.
    const totals = {};
    mos.forEach((m) => {
      Object.entries(spendingByMonth[m] || {}).forEach(([cat, val]) => {
        totals[cat] = (totals[cat] || 0) + val;
      });
    });

    const ranked = Object.entries(totals).sort((a, b) => b[1] - a[1]);
    const kept = ranked.filter(([c]) => !hidden.has(c));
    const sum = kept.reduce((acc, [, v]) => acc + v, 0);

    const head = kept.slice(0, TOP_N);
    const tail = kept.slice(TOP_N);
    const built = head.map(([category, amount]) => ({
      category,
      amount: +amount.toFixed(2),
      share: sum > 0 ? (amount / sum) * 100 : 0,
      isOther: false,
    }));
    if (tail.length) {
      const rest = tail.reduce((acc, [, v]) => acc + v, 0);
      built.push({
        // Named for the roll-up rather than "Other" so it can't be mistaken for
        // a real category that happens to be called that.
        category: `Other (${tail.length} more)`,
        amount: +rest.toFixed(2),
        share: sum > 0 ? (rest / sum) * 100 : 0,
        isOther: true,
      });
    }
    return { rows: built, total: sum, allRanked: ranked, months: mos };
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
          {allRanked.map(([cat, amt]) => {
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
                  <span className="eh-dcard-filter-amt">{fmt$(amt)}</span>
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
      <div className="eh-viz-summary">
        <strong>{fmt$(total)}</strong>
        <span>
          across {rows.length} {rows.length === 1 ? 'category' : 'categories'}
          {months.length ? ` · ${rangeLabel(months)}` : ''}
          {months.length > 1 ? ` (${months.length} mo total)` : ''}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={rows.length * ROW_H + CHART_PAD}>
        <BarChart
          data={rows}
          layout="vertical"
          margin={{ top: 0, right: 76, bottom: 0, left: 0 }}
          barCategoryGap={6}
        >
          <CartesianGrid
            horizontal={false}
            strokeDasharray="3 3"
            stroke="var(--border, #d1fae5)"
          />
          <XAxis
            type="number"
            tick={AXIS}
            tickFormatter={fmtTick}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="category"
            width={NAME_W}
            tick={<CategoryTick />}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: 'var(--bg-secondary, #d1fae5)', fillOpacity: 0.35 }}
            content={<SpendTooltip monthCount={months.length} />}
          />
          <Bar dataKey="amount" radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false}>
            {rows.map((r) => (
              <Cell key={r.category} fill={r.isOther ? BAR_FILL_OTHER : BAR_FILL} />
            ))}
            <LabelList
              dataKey="amount"
              position="right"
              offset={8}
              fontSize={11}
              fill="var(--text-secondary, #374151)"
              formatter={(v) => fmt$(v)}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </DashboardCard>
  );
}
