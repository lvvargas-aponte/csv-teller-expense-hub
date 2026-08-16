import React from 'react';
import {
  Area, ComposedChart, Legend, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

import { fmt$ } from '../../../utils/formatting';

const compact = (v) => {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${Math.round(v / 1_000)}k`;
  return `$${Math.round(v)}`;
};

/**
 * Income against need, over time.
 *
 * Stacked areas for the income sources and a line for what retirement
 * costs. The crossing point is the whole answer, so the retirement year is
 * marked rather than left to be inferred from where two shapes meet.
 */
export default function ProjectionChart({ rows, retirementYear }) {
  const data = rows.map((r) => ({
    year: r.year,
    Rental: r.rental_net,
    Withdrawals: r.withdrawal_capacity,
    'Social Security': r.social_security,
    Spending: r.spending_need,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <XAxis dataKey="year" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 11 }} width={56} tickFormatter={compact} />
        <Tooltip
          formatter={(value, name) => [fmt$(value), name]}
          labelFormatter={(l) => `Year ${l}`}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />

        <Area type="monotone" dataKey="Rental" stackId="income"
              stroke="#059669" fill="#059669" fillOpacity={0.75} />
        <Area type="monotone" dataKey="Withdrawals" stackId="income"
              stroke="#6366f1" fill="#6366f1" fillOpacity={0.7} />
        <Area type="monotone" dataKey="Social Security" stackId="income"
              stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.6} />

        <Line type="monotone" dataKey="Spending" stroke="#ef4444"
              strokeWidth={2} dot={false} />

        {retirementYear && (
          <ReferenceLine
            x={retirementYear}
            stroke="var(--text-primary)"
            strokeDasharray="4 4"
            label={{
              value: 'Retire', position: 'top',
              fontSize: 11, fill: 'var(--text-primary)',
            }}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
