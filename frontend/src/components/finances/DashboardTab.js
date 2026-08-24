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
import PortfolioCard from './cards/PortfolioCard';
import BudgetsCard from './cards/BudgetsCard';
import CreditUtilizationCard from './cards/CreditUtilizationCard';
import AlertsCard from './cards/AlertsCard';
import IncomeVsExpensesCard from './cards/IncomeVsExpensesCard';
import WeeklyDigestCard from './cards/WeeklyDigestCard';
import StandingCard from './cards/StandingCard';
import { BlurContext } from './Num';

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

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function monthName(monthKey) {
  const idx = parseInt((monthKey || '').slice(5, 7), 10) - 1;
  return MONTH_NAMES[idx] || 'the prior month';
}

export default function DashboardTab({ healthScore, healthSignals, onOpenSettings }) {
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

  // The backend bounds both months by the same day number, so this delta is
  // like-for-like all month long. Fall back to the raw month totals only for
  // a payload that predates spend_comparison.
  const spendComparison = dashboard?.spend_comparison || null;
  const thisMonth = spendComparison
    ? spendComparison.current_month_to_date
    : (monthlyTotals[monthlyTotals.length - 1]?.total ?? 0);
  const thisMonthDelta = spendComparison ? spendComparison.delta : null;

  const incomeRows = incomeData?.rows || [];
  const completeRows = incomeRows.filter((r) => r.is_partial !== true);
  // Nothing complete yet (a brand-new import, or the 1st of the month): show
  // the month in progress rather than an empty card, but without a delta.
  const incomeIsPartial = completeRows.length === 0 && incomeRows.length > 0;
  const kpiRows = incomeIsPartial ? incomeRows : completeRows;
  const latestIncome = kpiRows[kpiRows.length - 1];
  const incomeAmt = latestIncome?.income ?? 0;
  const expensesAmt = latestIncome?.expenses ?? 0;
  const netCashFlow = (latestIncome?.net) ?? (incomeAmt - expensesAmt);
  const prevIncomeRow = incomeIsPartial ? null : kpiRows[kpiRows.length - 2];
  const incomeDelta = prevIncomeRow ? incomeAmt - prevIncomeRow.income : null;
  const cashFlowDelta = prevIncomeRow ? netCashFlow - prevIncomeRow.net : null;

  const asOfDay = spendComparison?.as_of_day;
  const thisMonthHelp = spendComparison
    ? `Total spending in ${monthName(spendComparison.current_month)} through day ${asOfDay} (debits only). Compared with the first ${asOfDay} days of ${monthName(spendComparison.prior_month)} — a drop is good.`
    : 'Total spending so far in the current calendar month (debits only).';

  const kpiMonthName = monthName(latestIncome?.month);
  const incomeHelp = incomeIsPartial
    ? `Credits received in ${kpiMonthName} so far (paychecks, transfers in, refunds). The month is still in progress, so no month-over-month delta is shown.`
    : `Credits received in ${kpiMonthName} — the most recent complete month. The delta compares against the complete month before it.`;
  const cashFlowHelp = incomeIsPartial
    ? `Income minus expenses in ${kpiMonthName} so far. The month is still in progress, so no delta is shown.`
    : `Income minus expenses in ${kpiMonthName} — the most recent complete month. Positive means you saved; negative means you spent more than you earned.`;

  // "based on 4 of 5 signals" — the score is renormalized over whatever had
  // data, so how much of the model was covered belongs next to the number.
  const signalCount = healthSignals?.length ?? 0;
  const availableCount = healthSignals?.filter((s) => s.available).length ?? 0;
  const coverageLine = signalCount
    ? `Based on ${availableCount} of ${signalCount} signals.`
    : null;

  const netWorth = summary?.net_worth ?? trend?.current_net_worth ?? 0;
  const netWorthDelta = trend?.delta_30d ?? null;

  const today = useMemo(() => new Date(), []);
  const greetingLine = `${greetingFor(today)}, ${formatToday(today)}`;
  const bannerMsg = (() => {
    if (netWorthDelta !== null && netWorthDelta > 0) {
      return `Your net worth grew by ${fmt$(netWorthDelta)} this period 🎉`;
    }
    if (netWorthDelta !== null && netWorthDelta < 0) {
      return `Net worth dipped ${fmt$(netWorthDelta)} this period — let's see why.`;
    }
    return 'Welcome back to your dashboard';
  })();
  const bannerSub = (healthScore === null || healthScore === undefined)
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
          <div className="eh-banner-decor" aria-hidden="true" />
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
            <div className={`eh-banner-score${blurSensitive ? ' eh-blur' : ''}`}>
              <span>{(healthScore === null || healthScore === undefined) ? '—' : healthScore}</span>
              <span className="eh-info-wrap" tabIndex={0} aria-label="About the health score">
                <span className="eh-info-icon">i</span>
                <span className="eh-info-tooltip" role="tooltip">
                  <div className="eh-info-tooltip-title">Financial Health Score</div>
                  A 0–100 estimate of your overall financial position. Higher is better.
                  <div style={{ marginTop: 6, fontWeight: 600 }}>How it&apos;s calculated</div>
                  Each signal contributes a 0–1 sub-score scaled by its weight, then summed and divided by the weights that had data:
                  <ul>
                    <li><strong>Emergency runway (25%)</strong> — months of expenses your cash covers; your target scores 1.0, no cushion scores 0.</li>
                    <li><strong>Savings rate (25%)</strong> — share of income you keep; 20% or better scores 1.0, saving nothing scores 0.</li>
                    <li><strong>Credit utilization (20%)</strong> — balance ÷ limit across your cards; 0% scores 1.0, 80% or more scores 0.</li>
                    <li><strong>Debt-to-income (15%)</strong> — minimum payments ÷ income; 15% or less scores 1.0, 43% (the lending ceiling) scores 0.</li>
                    <li><strong>Net worth trend (15%)</strong> — 90-day change as a share of net worth; +5% scores 1.0, −5% scores 0.</li>
                  </ul>
                  {healthSignals?.length > 0 && (
                    <>
                      <div style={{ marginTop: 6, fontWeight: 600 }}>Yours right now</div>
                      <ul>
                        {healthSignals.map((s) => (
                          <li key={s.key}>
                            <strong>{s.label}</strong>
                            {s.available ? ` — ${s.detail}` : ` — skipped: ${s.detail}`}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                  {coverageLine}
                  {' '}Signals with no data are skipped; below half coverage no score is shown at all.
                </span>
              </span>
            </div>
            <div className="eh-banner-score-label">Health Score</div>
            {coverageLine && availableCount < signalCount && (
              <div className="eh-banner-score-coverage">{coverageLine}</div>
            )}
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
            help="Assets minus liabilities across all linked and manual accounts. The delta shows the change vs. 30 days ago."
          />
          <KpiCard
            label="This Month"
            value={fmt$(thisMonth)}
            delta={thisMonthDelta}
            deltaInverse
            barColor="#6366f1"
            blur={blurSensitive}
            help={thisMonthHelp}
          />
          <KpiCard
            label="Income"
            value={fmt$(incomeAmt)}
            delta={incomeDelta}
            barColor="#059669"
            blur={blurSensitive}
            inProgress={incomeIsPartial}
            help={incomeHelp}
          />
          <KpiCard
            label="Net Cash Flow"
            value={fmtSigned(netCashFlow)}
            valueClass={netCashFlow < 0 ? 'eh-kpi-value--neg' : 'eh-kpi-value--pos'}
            delta={cashFlowDelta}
            barColor={netCashFlow < 0 ? '#ef4444' : '#059669'}
            blur={blurSensitive}
            inProgress={incomeIsPartial}
            help={cashFlowHelp}
          />
        </section>

        {/* Cards grid — narrative arc: Position → Flow → Trend → Assets →
            Constraints → Commitments → Signals. Each card carries a section
            number; some span both columns for editorial rhythm. */}
        <BlurContext.Provider value={blurSensitive}>
          <section className={`eh-cards-grid${blurSensitive ? ' eh-blur-numbers' : ''}`}>
            {/* Where you stand — the answer the KPI row above only hints at. */}
            <div className="eh-card-full">
              <StandingCard onOpenSettings={onOpenSettings} />
            </div>
            <div className="eh-card-full">
              <WeeklyDigestCard />
            </div>
            <div className="eh-card-full">
              <NetWorthCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />
            </div>
            <CashFlowCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />
            <SpendingByCategoryCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />
            <div className="eh-card-full">
              <IncomeVsExpensesCard months={months} />
            </div>
            <BalancesCard summary={summary} loading={summaryLoading} error={summaryErr} />
            <PortfolioCard />
            <CreditUtilizationCard />
            <BudgetsCard />
            <div className="eh-card-full">
              <RecurringChargesCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />
            </div>
            <div className="eh-card-full">
              <AlertsCard />
            </div>
          </section>
        </BlurContext.Provider>
      </div>
    </>
  );
}

function KpiCard({ label, value, valueClass, delta, deltaInverse, barColor, blur, help, inProgress }) {
  let arrow = null;
  let deltaColor = 'var(--text-muted)';
  if ((delta !== null && delta !== undefined)) {
    const positive = delta >= 0;
    arrow = positive ? '↑' : '↓';
    const good = deltaInverse ? !positive : positive;
    deltaColor = good ? '#059669' : '#ef4444';
  }
  return (
    <div className="eh-kpi" role="group" aria-label={label}>
      <div className="eh-kpi-label">
        <span>{label}</span>
        {help && (
          <span className="eh-info-wrap eh-kpi-info" tabIndex={0} aria-label={`About ${label}`}>
            <span className="eh-info-icon">i</span>
            <span className="eh-info-tooltip" role="tooltip">
              <div className="eh-info-tooltip-title">{label}</div>
              {help}
            </span>
          </span>
        )}
      </div>
      <div className={`eh-kpi-value ${valueClass || ''}${blur ? ' eh-blur' : ''}`}>{value}</div>
      {(delta !== null && delta !== undefined) && (
        <div className="eh-kpi-delta" style={{ color: deltaColor }}>
          <span>{arrow}</span>
          <span className={blur ? 'eh-blur' : ''}>{fmt$(delta)}</span>
          <span className="eh-kpi-delta-suffix">vs prior</span>
        </div>
      )}
      {inProgress && (
        <div
          className="eh-kpi-inprogress"
          style={{
            fontSize: 12, fontWeight: 600, marginTop: 4,
            color: 'var(--text-muted)', fontStyle: 'italic',
          }}
        >
          Month in progress
        </div>
      )}
      <div className="eh-kpi-bar" style={{ background: barColor }} />
    </div>
  );
}
