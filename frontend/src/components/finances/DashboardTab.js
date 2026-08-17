import React, { useEffect, useMemo, useState } from 'react';
import { Responsive, WidthProvider } from 'react-grid-layout';

import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

import {
  getDashboard,
  getIncomeVsExpenses,
} from '../../api/dashboard';
import { getBalancesSummary } from '../../api/balances';
import { fmt$, fmtSigned, greetingFor, formatToday } from '../../utils/formatting';
import KpiCard from '../ui/KpiCard';

import NetWorthCard from './cards/NetWorthCard';
import CashFlowCard from './cards/CashFlowCard';
import SpendingByCategoryCard from './cards/SpendingByCategoryCard';
import RecurringChargesCard from './cards/RecurringChargesCard';
import BalancesCard from './cards/BalancesCard';
import PortfolioCard from './cards/PortfolioCard';
import BudgetsCard from './cards/BudgetsCard';
import GoalsCard from './cards/GoalsCard';
import CreditUtilizationCard from './cards/CreditUtilizationCard';
import AlertsCard from './cards/AlertsCard';
import IncomeVsExpensesCard from './cards/IncomeVsExpensesCard';
import useDashboardLayout, { DEFAULT_LAYOUT } from './dashboard/useDashboardLayout';
import { BlurContext } from './Num';

const ResponsiveGridLayout = WidthProvider(Responsive);

const RANGE_OPTIONS = [
  { label: '3M', months: 3 },
  { label: '6M', months: 6 },
  { label: '12M', months: 12 },
];

// The narrative arc, as data. `kicker` and `index` render as the card's
// eyebrow so the argument survives being rearranged — a user who moves
// Budgets above Balances still sees which chapter each card belongs to.
const CARD_META = {
  net_worth:       { index: 1,  kicker: 'Position',    title: 'Net worth' },
  cash_flow:       { index: 2,  kicker: 'Flow',        title: 'Cash flow' },
  spending:        { index: 3,  kicker: 'Flow',        title: 'Spending' },
  income_expenses: { index: 4,  kicker: 'Trend',       title: 'Income vs. expenses' },
  balances:        { index: 5,  kicker: 'Assets',      title: 'Balances' },
  portfolio:       { index: 6,  kicker: 'Assets',      title: 'Portfolio' },
  credit:          { index: 7,  kicker: 'Constraints', title: 'Credit' },
  budgets:         { index: 8,  kicker: 'Commitments', title: 'Budgets' },
  goals:           { index: 9,  kicker: 'Commitments', title: 'Goals' },
  recurring:       { index: 10, kicker: 'Commitments', title: 'Recurring' },
  alerts:          { index: 11, kicker: 'Signals',     title: 'Alerts' },
};

const CARD_ORDER = DEFAULT_LAYOUT.map((item) => item.i);

export default function DashboardTab({ healthScore }) {
  const {
    layout, hidden, editing, dirty,
    setEditing, handleLayoutChange, hide, show, persist, restoreDefaults,
  } = useDashboardLayout();
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
  const thisMonthDelta = (prevMonth !== null && prevMonth !== undefined) ? thisMonth - prevMonth : null;

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

  // ── Grid ─────────────────────────────────────────────────────────
  const visibleLayout = useMemo(
    () => layout.filter((item) => !hidden.includes(item.i)),
    [layout, hidden],
  );
  const hiddenCards = useMemo(
    () => CARD_ORDER.filter((id) => hidden.includes(id)),
    [hidden],
  );

  // `onHide` is passed only while arranging, so the × appears exactly when
  // it does something. Every card already forwards these three props.
  const renderCard = (id) => {
    const meta = CARD_META[id] || {};
    const shell = { ...meta, onHide: editing ? () => hide(id) : undefined };
    switch (id) {
      case 'net_worth':
        return <NetWorthCard {...shell} dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />;
      case 'cash_flow':
        return <CashFlowCard {...shell} dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />;
      case 'spending':
        return <SpendingByCategoryCard {...shell} dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />;
      case 'income_expenses':
        return <IncomeVsExpensesCard {...shell} months={months} />;
      case 'balances':
        return <BalancesCard {...shell} summary={summary} loading={summaryLoading} error={summaryErr} />;
      case 'portfolio':
        return <PortfolioCard {...shell} />;
      case 'credit':
        return <CreditUtilizationCard {...shell} />;
      case 'budgets':
        return <BudgetsCard {...shell} />;
      case 'goals':
        return <GoalsCard {...shell} />;
      case 'recurring':
        return <RecurringChargesCard {...shell} dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />;
      case 'alerts':
        return <AlertsCard {...shell} />;
      default:
        return null;
    }
  };

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
              {/* Dragging is off by default. The cards hold charts, buttons
                  and scrollable lists, and a grid that's always live turns
                  every stray drag into an accidental rearrangement. */}
              <button
                type="button"
                className="eh-banner-btn"
                onClick={() => { if (editing && dirty) persist(); setEditing(!editing); }}
              >
                {editing ? '✓ Done arranging' : '⠿ Arrange cards'}
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
                  Each signal contributes a 0–1 sub-score scaled by its weight, then summed and divided by the active weights:
                  <ul>
                    <li><strong>Net worth direction (30%)</strong> — 30-day Δ as a ratio of current net worth; positive growth scores higher.</li>
                    <li><strong>Credit utilization (30%)</strong> — overall balance ÷ limit across your cards; 0% scores 1.0, 100% scores 0. Skipped if you have no cards.</li>
                    <li><strong>Spending trend (40%)</strong> — this month vs. prior month; a drop scores above 0.5, a rise scores below.</li>
                  </ul>
                  Signals with no data are skipped, and remaining weights are renormalized. Score is recomputed when you sync new data or change the date range.
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
            help="Assets minus liabilities across all linked and manual accounts. The delta shows the change vs. 30 days ago."
          />
          <KpiCard
            label="This Month"
            value={fmt$(thisMonth)}
            delta={thisMonthDelta}
            deltaInverse
            barColor="#6366f1"
            blur={blurSensitive}
            help="Total spending so far in the current calendar month (debits only). The delta compares against the same point in the prior month — a drop is good."
          />
          <KpiCard
            label="Income"
            value={fmt$(incomeAmt)}
            delta={incomeDelta}
            barColor="#059669"
            blur={blurSensitive}
            help="Credits received in the most recent full month (paychecks, transfers in, refunds). The delta compares against the prior month."
          />
          <KpiCard
            label="Net Cash Flow"
            value={fmtSigned(netCashFlow)}
            valueClass={netCashFlow < 0 ? 'eh-kpi-value--neg' : 'eh-kpi-value--pos'}
            delta={cashFlowDelta}
            barColor={netCashFlow < 0 ? '#ef4444' : '#059669'}
            blur={blurSensitive}
            help="Income minus expenses for the most recent full month. Positive means you saved; negative means you spent more than you earned."
          />
        </section>

        {editing && (
          <section className="eh-arrange-bar">
            <span className="eh-arrange-hint">
              Drag to move, pull the bottom-right corner to resize, × to remove.
            </span>
            <div className="eh-arrange-actions">
              {hiddenCards.length > 0 && (
                <div className="eh-arrange-hidden">
                  {hiddenCards.map((id) => (
                    <button
                      key={id}
                      type="button"
                      className="eh-arrange-restore"
                      onClick={() => show(id)}
                    >
                      + {CARD_META[id]?.title || id}
                    </button>
                  ))}
                </div>
              )}
              <button type="button" className="eh-banner-btn" onClick={restoreDefaults}>
                Reset to default
              </button>
            </div>
          </section>
        )}

        {/* The narrative arc — Position → Flow → Trend → Assets →
            Constraints → Commitments → Signals — is the default arrangement,
            not a constraint. Each card keeps its chapter label wherever it
            lands. */}
        <BlurContext.Provider value={blurSensitive}>
          <div className={blurSensitive ? 'eh-blur-numbers' : undefined}>
            <ResponsiveGridLayout
              className="eh-grid"
              layouts={{ lg: visibleLayout, md: visibleLayout, sm: visibleLayout }}
              breakpoints={{ lg: 1200, md: 900, sm: 640, xs: 480, xxs: 0 }}
              cols={{ lg: 12, md: 12, sm: 6, xs: 4, xxs: 2 }}
              rowHeight={40}
              margin={[16, 16]}
              containerPadding={[0, 0]}
              isDraggable={editing}
              isResizable={editing}
              onLayoutChange={handleLayoutChange}
              draggableCancel="button, a, input, select, textarea"
            >
              {visibleLayout.map((item) => (
                <div key={item.i} className="eh-grid-item">
                  {renderCard(item.i)}
                </div>
              ))}
            </ResponsiveGridLayout>
          </div>
        </BlurContext.Provider>
      </div>
    </>
  );
}

