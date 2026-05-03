import React, { useEffect, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import { getIncomeVsExpenses } from '../../../api/dashboard';
import { fmt$ } from '../../../utils/formatting';

const AXIS = { fontSize: 11, fill: 'var(--text-secondary, #94a3b8)' };

export default function IncomeVsExpensesCard({ months = 6, onHide }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getIncomeVsExpenses(months)
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load income vs. expenses.'));
  }, [months]);

  const loading = data === null && !error;
  const rows = data?.rows || [];
  const empty = !loading && !error && rows.length === 0;

  const latest = rows[rows.length - 1];

  return (
    <DashboardCard
      title="Income vs. Expenses"
      loading={loading}
      error={error}
      empty={empty}
      emptyText="No transactions yet to compute income vs. expenses."
      onHide={onHide}
    >
      {latest && (
        <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 13 }}>
          <div>
            <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>Income</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#059669' }}>{fmt$(latest.income)}</div>
          </div>
          <div>
            <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>Expenses</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#ef4444' }}>{fmt$(latest.expenses)}</div>
          </div>
          <div>
            <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>Net</div>
            <div style={{
              fontSize: 16, fontWeight: 700,
              color: latest.net >= 0 ? '#10b981' : '#f87171',
            }}>
              {latest.net >= 0 ? '+' : '-'}{fmt$(latest.net)}
            </div>
          </div>
        </div>
      )}
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #334155)" />
          <XAxis dataKey="month" tick={AXIS} />
          <YAxis tick={AXIS} tickFormatter={(v) => fmt$(v)} width={70} />
          <Tooltip formatter={(v) => fmt$(v)} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="income" fill="#059669" fillOpacity={0.85} radius={[3, 3, 0, 0]} />
          <Bar dataKey="expenses" fill="#ef4444" fillOpacity={0.75} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </DashboardCard>
  );
}
