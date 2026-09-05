import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import { fmt$ } from '../../../utils/formatting';

// TOP_N (8) categories + an explicit 'Other' bucket = up to 9 series in the
// same stacked bar. Eight distinct hues so no two categories ever collide;
// 'Other' gets its own neutral token rather than falling out of the
// positional index, so it stays distinct even if TOP_N changes.
const PALETTE = [
  'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)',
  'var(--chart-5)', 'var(--chart-6)', 'var(--chart-7)', 'var(--chart-8)',
];
const OTHER_COLOR = 'var(--text-faint)';
const TOP_N = 8;
const AXIS = { fontSize: 11, fill: 'var(--text-faint)' };
const HIDDEN_KEY = 'dashboard.spendByCat.hidden';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

// Month keys are `YYYY-MM` from the dashboard payload, but the chart is fed
// whatever `months` holds — fall back to the raw key rather than guessing.
function monthLabel(key) {
  const m = /^(\d{4})-(\d{2})$/.exec(key || '');
  if (!m) return key || '';
  return `${MONTH_NAMES[Number(m[2]) - 1] || m[2]} ${m[1]}`;
}

// A category that spent nothing last month has no percentage to move by;
// "New" says that more honestly than a division by zero.
function deltaFor(current, previous) {
  if (!previous) return { text: 'New', tone: 'up' };
  const pct = ((current - previous) / previous) * 100;
  if (Math.abs(pct) < 1) return { text: 'Flat', tone: 'flat' };
  return {
    text: `${pct > 0 ? '↑' : '↓'} ${Math.abs(Math.round(pct))}%`,
    tone: pct > 0 ? 'up' : 'down',
  };
}

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
  // Null means "follow the latest month". Changing the range replaces the
  // month list, so a pinned month that falls outside it is dropped rather
  // than left showing a column the chart no longer draws.
  const [pinnedMonth, setPinnedMonth] = useState(null);

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

  const months = useMemo(() => dashboard?.months || [], [dashboard]);
  const selectedMonth = months.includes(pinnedMonth)
    ? pinnedMonth
    : months[months.length - 1];

  // The drill-down lists every category the month actually has, not the
  // chart's top-8 + Other — collapsing them here would hide exactly what a
  // drill-down is for. Colours still come from the chart's ranking so a row
  // and its band in the bar read as the same thing; everything past TOP_N
  // shares the neutral 'Other' swatch, which is the band it sits in.
  const drill = useMemo(() => {
    const byMonth = dashboard?.spending_by_month || {};
    const current = byMonth[selectedMonth] || {};
    const previous = byMonth[months[months.indexOf(selectedMonth) - 1]];
    const entries = Object.entries(current)
      .filter(([cat, val]) => !hidden.has(cat) && val > 0)
      .sort((a, b) => b[1] - a[1]);
    const max = entries.length ? entries[0][1] : 0;
    const total = entries.reduce((sum, [, val]) => sum + val, 0);
    return {
      total,
      items: entries.map(([cat, val]) => {
        const rank = keys.indexOf(cat);
        return {
          cat,
          val,
          share: max ? (val / max) * 100 : 0,
          color: rank >= 0 && cat !== 'Other' ? PALETTE[rank % PALETTE.length] : OTHER_COLOR,
          // No prior month in the window means there is nothing to compare
          // against; a category simply missing from one that exists is a
          // real zero, and reads as "New".
          delta: previous ? deltaFor(val, previous[cat] || 0) : null,
        };
      }),
    };
  }, [dashboard, months, selectedMonth, hidden, keys]);

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
        <BarChart
          data={rows}
          onClick={(st) => st?.activeLabel && setPinnedMonth(st.activeLabel)}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="month" tick={AXIS} />
          <YAxis tick={AXIS} tickFormatter={(v) => fmt$(v)} width={70} />
          <Tooltip formatter={(v) => fmt$(v)} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {keys.map((cat, i) => (
            <Bar key={cat} dataKey={cat} stackId="spend" fill={cat === 'Other' ? OTHER_COLOR : PALETTE[i % PALETTE.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>

      <div className="eh-spendcat-drill">
        <div className="eh-spendcat-head">
          {/* Clicking a bar picks the month too, but that is mouse-only —
              the select is the keyboard path to the same state. */}
          <select
            className="eh-spendcat-month"
            aria-label="Month to break down"
            value={selectedMonth || ''}
            onChange={(e) => setPinnedMonth(e.target.value)}
          >
            {months.map((m) => (
              <option key={m} value={m}>{monthLabel(m)}</option>
            ))}
          </select>
          <span className="eh-spendcat-total">{fmt$(drill.total)}</span>
        </div>
        {drill.items.length === 0 ? (
          <p className="eh-spendcat-none">No spending in {monthLabel(selectedMonth)}.</p>
        ) : (
          <ul className="eh-spendcat-list" aria-label="Category breakdown">
            {drill.items.map(({ cat, val, share, color, delta }) => (
              <li key={cat} className="eh-spendcat-row">
                <span className="eh-spendcat-swatch" style={{ background: color }} />
                <span className="eh-spendcat-name" title={cat}>{cat}</span>
                <span className="eh-spendcat-bar">
                  <span
                    className="eh-spendcat-fill"
                    style={{ width: `${share}%`, background: color }}
                  />
                </span>
                <span className="eh-spendcat-amt">{fmt$(val)}</span>
                <span className={`eh-spendcat-delta eh-spendcat-delta--${delta ? delta.tone : 'none'}`}>
                  {delta ? delta.text : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </DashboardCard>
  );
}