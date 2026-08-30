import React, { useEffect, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import DashboardCard from './DashboardCard';
import Spin from '../../ui/Spin';
import { getCashflowProjection } from '../../../api/cashflow';
import { getIncomeVsExpenses } from '../../../api/dashboard';
import { fmt$ } from '../../../utils/formatting';
import Num, { BlurMoney } from '../Num';

const AXIS = { fontSize: 11, fill: 'var(--text-faint, #9ca3af)' };
const AXIS_IVE = { fontSize: 11, fill: 'var(--text-secondary, #94a3b8)' };

// Bars keep the saturated fill; the figures beside them use the text-grade
// sibling, which is the only one that clears 4.5:1 on the white card.
const IN_FILL = 'var(--accent)';
const OUT_FILL = 'var(--amber)';
const NEG_FILL = 'var(--red)';
const IN_TEXT = 'var(--status-good-text)';
const OUT_TEXT = 'var(--status-warn-text)';
const NEG_TEXT = 'var(--status-bad-text)';

const CONFIDENCE_NOTE = {
  high: 'median of your last three complete months',
  low: 'rough — two months of history',
};

const subHeadingStyle = { margin: '0 0 8px', fontSize: 13, fontWeight: 700 };
const sectionStyle = { marginTop: 20 };

function OutlookSection() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCashflowProjection(30)
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load the cash-flow outlook.'));
  }, []);

  const loading = data === null && !error;
  const horizon = data?.horizon_days ?? 30;
  const moneyIn = (data?.expected_income || 0) + (data?.expected_inbound_transfers || 0);
  const recurring = data?.expected_recurring_outflow || 0;
  const discretionary = data?.expected_discretionary_outflow || 0;
  const net = data?.net || 0;
  const confidence = data?.discretionary_basis?.confidence;
  const incomplete = data?.projection_incomplete === true;
  const empty = !loading && !error && moneyIn === 0 && recurring === 0 && discretionary === 0;

  const rows = [
    { key: 'in', label: 'Money in', value: moneyIn, fill: IN_FILL, text: IN_TEXT },
    { key: 'recurring', label: 'Recurring bills', value: -recurring, fill: OUT_FILL, text: OUT_TEXT },
  ];
  if (!incomplete) {
    rows.push({
      key: 'discretionary',
      label: 'Typical spending',
      value: -discretionary,
      fill: OUT_FILL,
      text: OUT_TEXT,
      note: CONFIDENCE_NOTE[confidence],
    });
  }
  rows.push({
    key: 'net',
    label: 'Projected net',
    value: net,
    fill: net < 0 ? NEG_FILL : IN_FILL,
    text: net < 0 ? NEG_TEXT : IN_TEXT,
    emphasis: true,
  });

  const widest = Math.max(...rows.map((r) => Math.abs(r.value)), 1);

  return (
    <section style={sectionStyle} aria-busy={loading}>
      <h3 style={subHeadingStyle}>{`${horizon}-Day Outlook`}</h3>
      {loading && (
        <div className="eh-dcard-state"><Spin /> Loading…</div>
      )}
      {error && !loading && (
        <div className="eh-dcard-state eh-dcard-state--error">{error}</div>
      )}
      {empty && !loading && !error && (
        <div className="eh-dcard-state eh-dcard-state--empty">
          Not enough history yet to project the next month.
        </div>
      )}
      {!loading && !error && !empty && (
        <>
          <div style={{ display: 'grid', gap: 10 }}>
            {rows.map((r) => (
              <div key={r.key}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span style={{ fontWeight: r.emphasis ? 700 : 500 }}>{r.label}</span>
                  <span style={{ color: r.text, fontWeight: r.emphasis ? 700 : 500 }}>
                    <Num value={r.value} signed prefix={r.value >= 0 ? '+' : ''} />
                    <span className="sr-only">{r.value < 0 ? ' out' : ' in'}</span>
                  </span>
                </div>
                <div
                  style={{ height: 6, background: 'var(--border, #334155)', borderRadius: 3, marginTop: 3 }}
                  aria-hidden="true"
                >
                  <div style={{
                    height: '100%',
                    width: `${Math.min(100, (Math.abs(r.value) / widest) * 100)}%`,
                    background: r.fill,
                    borderRadius: 3,
                  }} />
                </div>
                {r.note && (
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{r.note}</div>
                )}
              </div>
            ))}
          </div>

          {net < 0 && (
            <div style={{ fontSize: 12, color: NEG_TEXT, marginTop: 10, fontWeight: 600 }}>
              <BlurMoney
                text={`Spending is projected to exceed income by about $${Math.round(Math.abs(net)).toLocaleString()} over the next ${horizon} days.`}
              />
            </div>
          )}

          {incomplete && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 10 }}>
              Typical spending isn&apos;t counted yet — under two complete months of history, so this
              projection is incomplete and covers bills only.
            </div>
          )}

          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 10 }}>
            An estimate from your recent months, not a promise. Bills are projected from the day of
            the month each one usually lands.
          </div>
        </>
      )}
    </section>
  );
}

function IncomeVsExpensesSection({ months }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null);
    setError(null);
    getIncomeVsExpenses(months)
      .then((r) => setData(r.data))
      .catch(() => setError('Could not load income vs. expenses.'));
  }, [months]);

  const loading = data === null && !error;
  const rows = data?.rows || [];
  const empty = !loading && !error && rows.length === 0;
  const latest = rows[rows.length - 1];

  return (
    <section style={sectionStyle} aria-busy={loading}>
      <h3 style={subHeadingStyle}>Income vs. Expenses</h3>
      {loading && (
        <div className="eh-dcard-state"><Spin /> Loading…</div>
      )}
      {error && !loading && (
        <div className="eh-dcard-state eh-dcard-state--error">{error}</div>
      )}
      {empty && !loading && !error && (
        <div className="eh-dcard-state eh-dcard-state--empty">
          No transactions yet to compute income vs. expenses.
        </div>
      )}
      {!loading && !error && !empty && (
        <>
          {latest && (
            <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 13 }}>
              <div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>Income</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--status-good-text)' }}><Num value={latest.income} /></div>
              </div>
              <div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>Expenses</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--status-bad-text)' }}><Num value={latest.expenses} /></div>
              </div>
              <div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>Net</div>
                <div style={{
                  fontSize: 16, fontWeight: 700,
                  color: latest.net >= 0 ? 'var(--status-good-text)' : 'var(--status-bad-text)',
                }}>
                  <Num value={latest.net} prefix={latest.net >= 0 ? '+' : '-'} />
                </div>
              </div>
            </div>
          )}
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #334155)" />
              <XAxis dataKey="month" tick={AXIS_IVE} />
              <YAxis tick={AXIS_IVE} tickFormatter={(v) => fmt$(v)} width={70} />
              <Tooltip formatter={(v) => fmt$(v)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="income" fill="#059669" fillOpacity={0.85} radius={[3, 3, 0, 0]} />
              <Bar dataKey="expenses" fill="#ef4444" fillOpacity={0.75} radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </>
      )}
    </section>
  );
}

export default function CashFlowCard({
  dashboard, loading, error, onHide, index, kicker, months,
}) {
  const totals = dashboard?.monthly_totals || [];
  const empty = !loading && !error && totals.length === 0;

  const latest = totals[totals.length - 1]?.total ?? 0;
  const prev = totals[totals.length - 2]?.total ?? null;
  const delta = (prev !== null && prev !== undefined) ? latest - prev : null;
  const high = latest >= 12000;

  return (
    <DashboardCard
      title="Cash Flow"
      index={index}
      kicker={kicker}
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
          color: high ? 'var(--status-bad-text)' : 'var(--status-good-text)',
        }}>
          {high ? 'High' : 'On track'}
        </span>
      }
    >
      <section>
        <h3 style={subHeadingStyle}>Monthly Spending</h3>
        <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 13 }}>
          <div>
            <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>This month</div>
            <div style={{ fontSize: 19, fontWeight: 700, fontFamily: "'DM Mono', monospace" }}>
              <Num value={latest} />
            </div>
          </div>
          {(delta !== null && delta !== undefined) && (
            <div>
              <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>vs. last</div>
              <div style={{
                fontSize: 19, fontWeight: 700,
                color: delta <= 0 ? 'var(--status-good-text)' : 'var(--status-bad-text)',
                fontFamily: "'DM Mono', monospace",
              }}>
                <Num value={delta} prefix={delta >= 0 ? '+' : '-'} />
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
      </section>

      <OutlookSection />
      <IncomeVsExpensesSection months={months} />
    </DashboardCard>
  );
}
