import React, { useEffect, useMemo, useState } from 'react';

import {
  getDashboard,
  getIncomeVsExpenses,
} from '../../api/dashboard';
import { getBalancesSummary } from '../../api/balances';
import { fmt$, fmtSigned } from '../../utils/formatting';

import NetWorthCard from './cards/NetWorthCard';
import CashFlowCard from './cards/CashFlowCard';
import SpendingByCategoryCard from './cards/SpendingByCategoryCard';
import RecurringChargesCard from './cards/RecurringChargesCard';
import BalancesCard from './cards/BalancesCard';
import BudgetsCard from './cards/BudgetsCard';
import CreditUtilizationCard from './cards/CreditUtilizationCard';
import AlertsCard from './cards/AlertsCard';
import IncomeVsExpensesCard from './cards/IncomeVsExpensesCard';
import TweaksPanel from './TweaksPanel';

const RANGE_OPTIONS = [
  { label: '3M', months: 3 },
  { label: '6M', months: 6 },
  { label: '12M', months: 12 },
];

function greetingFor(date) {
  const h = date.getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

function formatToday(date) {
  return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric' });
}

export default function DashboardTab({ healthScore }) {
  const [months, setMonths] = useState(6);
  const [dashboard, setDashboard] = useState(null);
  const [dashboardErr, setDashboardErr] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);

  const [summary, setSummary] = useState(null);
  const [summaryErr, setSummaryErr] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  const [incomeData, setIncomeData] = useState(null);

  const [blurSensitive, setBlurSensitive] = useState(
    () => localStorage.getItem('eh.blurSensitive') === 'true'
  );

  useEffect(() => {
    localStorage.setItem('eh.blurSensitive', String(blurSensitive));
  }, [blurSensitive]);

  useEffect(() => {
    setDashboardLoading(true);
    setDashboardErr(null);
    getDashboard(months)
      .then((r) => setDashboard(r.data))
      .catch(() => setDashboardErr('Could not load dashboard data.'))
      .finally(() => setDashboardLoading(false));
  }, [months]);

  useEffect(() => {
    setSummaryLoading(true);
    setSummaryErr(null);
    getBalancesSummary(false)
      .then((r) => setSummary(r.data))
      .catch(() => setSummaryErr('Could not load balances.'))
      .finally(() => setSummaryLoading(false));
  }, []);

  useEffect(() => {
    getIncomeVsExpenses(months).then((r) => setIncomeData(r.data)).catch(() => {});
  }, [months]);

  // ── Derived banner + KPI values ──────────────────────────────────
  const trend = dashboard?.balance_trend;
  const monthlyTotals = dashboard?.monthly_totals || [];
  const thisMonth = monthlyTotals[monthlyTotals.length - 1]?.total ?? 0;
  const prevMonth = monthlyTotals[monthlyTotals.length - 2]?.total ?? null;
  const thisMonthDelta = prevMonth != null ? thisMonth - prevMonth : null;

  const incomeRows = incomeData?.rows || [];
  const latestIncome = incomeRows[incomeRows.length - 1];
  const incomeAmt = latestIncome?.income ?? 0;
  const expensesAmt = latestIncome?.expenses ?? 0;
  const netCashFlow = (latestIncome?.net) ?? (incomeAmt - expensesAmt);
  const prevIncomeRow = incomeRows[incomeRows.length - 2];
  const incomeDelta = prevIncomeRow ? incomeAmt - prevIncomeRow.income : null;
  const cashFlowDelta = prevIncomeRow ? netCashFlow - prevIncomeRow.net : null;

  const netWorth = summary?.net_worth ?? trend?.current_net_worth ?? 0;
  const netWorthDelta = trend?.delta_30d ?? null;

  const today = useMemo(() => new Date(), []);
  const greetingLine = `${greetingFor(today)}, ${formatToday(today)}`;
  const bannerMsg = (() => {
    if (netWorthDelta != null && netWorthDelta > 0) {
      return `Your net worth grew by ${fmt$(netWorthDelta)} this period 🎉`;
    }
    if (netWorthDelta != null && netWorthDelta < 0) {
      return `Net worth dipped ${fmt$(netWorthDelta)} this period — let's see why.`;
    }
    return 'Welcome back to your dashboard';
  })();
  const bannerSub = healthScore == null
    ? 'Sync accounts or import transactions to start tracking your health.'
    : healthScore >= 70
      ? "You're on solid footing — keep it up."
      : healthScore >= 50
        ? 'Small adjustments now compound over time.'
        : 'A few gentle nudges could move the needle.';

  return (
    <>
      <div className="eh-topbar">
        <div className="eh-topbar-title">Dashboard</div>
        <div className="eh-range-pill" role="tablist" aria-label="Date range">
          {RANGE_OPTIONS.map((r) => (
            <button
              key={r.label}
              type="button"
              role="tab"
              aria-selected={months === r.months}
              className={months === r.months ? 'eh-range-pill--active' : ''}
              onClick={() => setMonths(r.months)}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="eh-content">
        {/* Health banner */}
        <section className="eh-banner">
          <div className="eh-banner-left">
            <div className="eh-banner-greet">{greetingLine}</div>
            <div className="eh-banner-msg">{bannerMsg}</div>
            <div className="eh-banner-sub">{bannerSub}</div>
            <div className="eh-banner-actions">
              <button type="button" className="eh-banner-btn"
                      onClick={() => setBlurSensitive((b) => !b)}>
                {blurSensitive ? '👁 Show numbers' : '🙈 Hide numbers'}
              </button>
            </div>
          </div>
          <div className="eh-banner-right">
            <div className="eh-banner-score">
              <span>{healthScore == null ? '—' : healthScore}</span>
              <span className="eh-info-wrap" tabIndex={0} aria-label="About the health score">
                <span className="eh-info-icon">i</span>
                <span className="eh-info-tooltip" role="tooltip">
                  <div className="eh-info-tooltip-title">Financial Health Score</div>
                  A 0–100 estimate of your overall financial position. Higher is better.
                  <ul>
                    <li>Net worth direction (recent change)</li>
                    <li>Credit utilization (lower is better)</li>
                    <li>Monthly spending trend (vs. prior month)</li>
                  </ul>
                  Score is recomputed when you sync new data or change the date range.
                </span>
              </span>
            </div>
            <div className="eh-banner-score-label">Health Score</div>
          </div>
        </section>

        {/* KPI row */}
        <section className="eh-kpi-row">
          <KpiCard
            label="Net Worth"
            value={fmtSigned(netWorth)}
            valueClass={netWorth < 0 ? 'eh-kpi-value--neg' : 'eh-kpi-value--pos'}
            delta={netWorthDelta}
            barColor={netWorth < 0 ? '#ef4444' : '#059669'}
            blur={blurSensitive}
          />
          <KpiCard
            label="This Month"
            value={fmt$(thisMonth)}
            delta={thisMonthDelta}
            deltaInverse
            barColor="#6366f1"
            blur={blurSensitive}
          />
          <KpiCard
            label="Income"
            value={fmt$(incomeAmt)}
            delta={incomeDelta}
            barColor="#059669"
            blur={blurSensitive}
          />
          <KpiCard
            label="Net Cash Flow"
            value={fmtSigned(netCashFlow)}
            valueClass={netCashFlow < 0 ? 'eh-kpi-value--neg' : 'eh-kpi-value--pos'}
            delta={cashFlowDelta}
            barColor={netCashFlow < 0 ? '#ef4444' : '#059669'}
            blur={blurSensitive}
          />
        </section>

        {/* Cards grid — order locked to design */}
        <section className="eh-cards-grid">
          <NetWorthCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />
          <CashFlowCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />
          <SpendingByCategoryCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />
          <IncomeVsExpensesCard months={months} />
          <BalancesCard summary={summary} loading={summaryLoading} error={summaryErr} />
          <CreditUtilizationCard />
          <div className="eh-card-full">
            <RecurringChargesCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />
          </div>
          <AlertsCard />
          <BudgetsCard />
        </section>
      </div>

      <TweaksPanel
        blurSensitive={blurSensitive}
        onBlurChange={setBlurSensitive}
      />
    </>
  );
}

function KpiCard({ label, value, valueClass, delta, deltaInverse, barColor, blur }) {
  let arrow = null;
  let deltaColor = 'var(--text-muted)';
  if (delta != null) {
    const positive = delta >= 0;
    arrow = positive ? '↑' : '↓';
    const good = deltaInverse ? !positive : positive;
    deltaColor = good ? '#059669' : '#ef4444';
  }
  return (
    <div className="eh-kpi">
      <div className="eh-kpi-label">{label}</div>
      <div className={`eh-kpi-value ${valueClass || ''}${blur ? ' eh-blur' : ''}`}>{value}</div>
      {delta != null && (
        <div className="eh-kpi-delta" style={{ color: deltaColor }}>
          <span>{arrow}</span>
          <span>{fmt$(delta)}</span>
          <span className="eh-kpi-delta-suffix">vs prior</span>
        </div>
      )}
      <div className="eh-kpi-bar" style={{ background: barColor }} />
    </div>
  );
}
