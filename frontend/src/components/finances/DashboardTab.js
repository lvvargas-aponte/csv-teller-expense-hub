import React, { useEffect, useMemo, useState } from 'react';

import {
  getDashboard,
  getCreditHealth,
} from '../../api/dashboard';
import { getAfterTaxNetWorth } from '../../api/tax';
import { getRatios } from '../../api/health';

import BalanceSheetHero from './BalanceSheetHero';
import NetWorthCard from './cards/NetWorthCard';
import CashFlowCard from './cards/CashFlowCard';
import SpendingByCategoryCard from './cards/SpendingByCategoryCard';
import BudgetsCard from './cards/BudgetsCard';
import UpcomingBillsCard from './cards/UpcomingBillsCard';
import NeedsYouFeed from './NeedsYouFeed';
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

export default function DashboardTab({
  healthScore, healthSignals, onNavigate,
  // Balances are fetched once by FinancesPage, which needs them for the
  // sidebar anyway; the dashboard used to request the same payload again on
  // the landing view. The `months` range stays owned here.
  summary, onInsightAction, currentPath,
}) {
  const [months, setMonths] = useState(6);
  // Grouped totals are a view of the same data, so this refetches rather
  // than reshaping what is already on screen.
  const [rolledUp, setRolledUp] = useState(
    () => localStorage.getItem('eh.rolledUp') === 'true',
  );
  const [dashboard, setDashboard] = useState(null);
  const [dashboardErr, setDashboardErr] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(true);


  const [blurSensitive, setBlurSensitive] = useState(
    () => localStorage.getItem('eh.blurSensitive') === 'true'
  );

  useEffect(() => {
    localStorage.setItem('eh.blurSensitive', String(blurSensitive));
  }, [blurSensitive]);

  useEffect(() => {
    setDashboardLoading(true);
    setDashboardErr(null);
    getDashboard(months, rolledUp)
      .then((r) => setDashboard(r.data))
      .catch(() => setDashboardErr('Could not load dashboard data.'))
      .finally(() => setDashboardLoading(false));
  }, [months, rolledUp]);

  useEffect(() => {
    localStorage.setItem('eh.rolledUp', String(rolledUp));
  }, [rolledUp]);

  // Opt-in and unavailable by default, so a failure here is indistinguishable
  // from the setting being off — both mean "don't render the line".
  const [afterTax, setAfterTax] = useState(null);
  useEffect(() => {
    getAfterTaxNetWorth().then((r) => setAfterTax(r.data)).catch(() => setAfterTax(null));
  }, []);

  // "Where you stand" is absorbed into Needs You; only its headline figure —
  // how long the cash on hand lasts — earns a spot beside the health score.
  const [ratios, setRatios] = useState(null);
  useEffect(() => {
    getRatios().then((r) => setRatios(r.data)).catch(() => setRatios(null));
  }, []);

  // Utilization joins the hero's readings. Computed server-side over the same
  // composition /debt reads, so the two pages cannot disagree.
  const [creditHealth, setCreditHealth] = useState(null);
  useEffect(() => {
    getCreditHealth().then((r) => setCreditHealth(r.data)).catch(() => setCreditHealth(null));
  }, []);

  // ── Derived values ───────────────────────────────────────────────
  // A late sync is a fact about the page, not a spending result. The old
  // "This Month" tile divided an empty month by a full one and reported a
  // 100% drop every time a sync ran late, which is the most alarming way to
  // say "no data yet".
  const spendComparison = dashboard?.spend_comparison || null;
  const syncIsStale = !!(
    spendComparison
    && spendComparison.current_month_is_partial
    && spendComparison.as_of_day > 1
    && spendComparison.current_month_to_date === 0
  );
  const staleSinceMonth = syncIsStale ? monthName(spendComparison.prior_month) : null;
  const staleCurrentMonth = syncIsStale ? monthName(spendComparison.current_month) : null;

  const today = useMemo(() => new Date(), []);
  const greetingLine = `${greetingFor(today)}, ${formatToday(today)}`;

  return (
    <>
      <div className="eh-topbar">
        <div>
          <h1 className="eh-topbar-title">Home</h1>
          <div className="eh-topbar-date">{greetingLine}</div>
        </div>
        <div className="eh-topbar-controls">
          <button
            type="button"
            className="eh-topbar-blur"
            onClick={() => setBlurSensitive((b) => !b)}
          >
            {blurSensitive ? 'Show numbers' : 'Hide numbers'}
          </button>
          {/* A filter group, not tabs: the ARIA tab pattern promises arrow-key
              navigation and a matching tabpanel, and neither exists here. */}
          <button
            type="button"
            className={`eh-toolbar-btn${rolledUp ? ' eh-toolbar-btn--on' : ''}`}
            aria-pressed={rolledUp}
            title="Report categories under their parent group where one is set"
            onClick={() => setRolledUp((v) => !v)}
          >
            {rolledUp ? 'Grouped' : 'By category'}
          </button>
          <div className="eh-range-pill" role="group" aria-label="Date range">
            {RANGE_OPTIONS.map((r) => (
              <button
                key={r.label}
                type="button"
                aria-pressed={months === r.months}
                className={months === r.months ? 'eh-range-pill--active' : ''}
                onClick={() => setMonths(r.months)}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="eh-content">
        <BalanceSheetHero
          summary={summary}
          healthScore={healthScore}
          healthSignals={healthSignals}
          ratios={ratios}
          creditHealth={creditHealth}
          blur={blurSensitive}
        />

        {syncIsStale && (
          <div className="eh-stale" role="status">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l3 2" />
            </svg>
            <span>
              Nothing has synced since {staleSinceMonth}, so {staleCurrentMonth} is
              empty — not a drop in spending.
            </span>
          </div>
        )}

        <BlurContext.Provider value={blurSensitive}>
          {/* Two regions, each stacking on its own, rather than cells of one
              grid — a grid row is as tall as its tallest member, and Cash Flow
              held its row open and left a hole beside it.
              Upcoming Bills leads the side region so it sits beside Needs You;
              Cash Flow, by far the tallest card, goes under it where the only
              thing it can push is itself. */}
          <section className={`eh-cards-grid${blurSensitive ? ' eh-blur-numbers' : ''}`}>
            <div className="eh-card-main">
              {/* What needs you is what you read first. */}
              <NeedsYouFeed summary={summary} dashboard={dashboard} onNavigate={onInsightAction} currentPath={currentPath} />
              <NetWorthCard dashboard={dashboard} summary={summary} afterTax={afterTax} loading={dashboardLoading} error={dashboardErr} />
              <div className="eh-card-pair">
                <SpendingByCategoryCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} />
                <BudgetsCard />
              </div>
            </div>
            <div className="eh-card-side">
              <UpcomingBillsCard onNavigateToAccounts={() => onNavigate?.('debt')} />
              <CashFlowCard dashboard={dashboard} loading={dashboardLoading} error={dashboardErr} months={months} />
            </div>
          </section>
        </BlurContext.Provider>
      </div>
    </>
  );
}
