import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import FinancesSidebar from './FinancesSidebar';
import DashboardTab from './DashboardTab';
import AccountsTab from './AccountsTab';
import InvestmentsTab from './InvestmentsTab';
import BalancesSection from './BalancesSection';
import PayoffPlanner from './PayoffPlanner';
import SpendingInsights from './SpendingInsights';
import BudgetsSection from './BudgetsSection';
import GoalsSection from './GoalsSection';
import ProfileSection from './ProfileSection';
import AdvisorChat from './AdvisorChat';
import KnowledgeSection from './KnowledgeSection';
import RecurringChargesCard from './cards/RecurringChargesCard';
import UpcomingBillsCard from './cards/UpcomingBillsCard';
import { getDashboard, getCreditHealth } from '../../api/dashboard';
import { getBalancesSummary } from '../../api/balances';

const ACTIVE_TAB_KEY = 'finances.activeTab';

export default function FinancesPage() {
  const [activeId, setActiveIdState] = useState(
    () => localStorage.getItem(ACTIVE_TAB_KEY) || 'dashboard',
  );
  const setActiveId = useCallback((id) => {
    setActiveIdState(id);
    try { localStorage.setItem(ACTIVE_TAB_KEY, id); } catch { /* quota / private mode */ }
  }, []);
  const navigate = useNavigate();

  const handleInsightAction = useCallback((target) => {
    if (!target) return;
    if (target.financesTab) setActiveId(target.financesTab);
    if (target.route)       navigate(target.route);
  }, [navigate, setActiveId]);

  // Shared signals used by the sidebar's Financial Health footer.
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [creditHealth, setCreditHealth] = useState(null);

  const loadBalances = useCallback((force = false) => {
    setSummaryLoading(true);
    setSummaryError(null);
    getBalancesSummary(force)
      .then((r) => setSummary(r.data))
      .catch(() => setSummaryError('Could not load balances — is the backend running?'))
      .finally(() => setSummaryLoading(false));
  }, []);

  useEffect(() => {
    loadBalances(false);
    getDashboard(6).then((r) => setDashboard(r.data)).catch(() => {});
    getCreditHealth().then((r) => setCreditHealth(r.data)).catch(() => {});
  }, [loadBalances]);

  const healthScore = computeHealthScore({
    netWorth: summary?.net_worth,
    trend: dashboard?.balance_trend,
    creditHealth,
    monthlyTotals: dashboard?.monthly_totals,
  });

  const creditAccounts = useMemo(
    () => summary?.accounts?.filter(
      (a) => a.type === 'credit' && Math.abs(parseFloat(a.ledger) || 0) >= 0.005,
    ) ?? [],
    [summary],
  );

  const handleNavigate = useCallback((id) => {
    setActiveId(id);
  }, [setActiveId]);

  return (
    <div className="eh-app">
      <FinancesSidebar
        activeId={activeId}
        onNavigate={handleNavigate}
        healthScore={healthScore}
      />

      <div className="eh-main">
        {activeId === 'dashboard' && (
          <DashboardTab healthScore={healthScore} />
        )}

        {activeId === 'overview' && (
          <SimplePage title="Overview">
            <BalancesSection
              summary={summary}
              loading={summaryLoading}
              error={summaryError}
              onRefresh={() => loadBalances(true)}
              onMutate={() => loadBalances(false)}
            />
            <SpendingInsights
              summary={summary}
              dashboard={dashboard}
              onNavigate={handleInsightAction}
            />
          </SimplePage>
        )}

        {activeId === 'accounts' && (
          <SimplePage title="Accounts">
            <AccountsTab
              summary={summary}
              summaryLoading={summaryLoading}
              summaryError={summaryError}
              onRefresh={() => loadBalances(true)}
            />
            <ProfileSection />
          </SimplePage>
        )}

        {activeId === 'investments' && (
          <SimplePage title="Investments"><InvestmentsTab /></SimplePage>
        )}

        {activeId === 'budgets' && (
          <SimplePage title="Budgets"><BudgetsSection /></SimplePage>
        )}

        {activeId === 'goals' && (
          <SimplePage title="Goals"><GoalsSection /></SimplePage>
        )}

        {activeId === 'bills' && (
          <SimplePage title="Bills">
            <div style={{ display: 'grid', gap: 16 }}>
              <UpcomingBillsCard onNavigateToAccounts={() => setActiveId('accounts')} />
              <RecurringChargesCard variant="detail" />
            </div>
          </SimplePage>
        )}

        {activeId === 'debt-payoff' && (
          <SimplePage title="Debt Payoff">
            <PayoffPlanner creditAccounts={creditAccounts} />
          </SimplePage>
        )}

        {activeId === 'knowledge' && (
          <SimplePage title="Knowledge"><KnowledgeSection /></SimplePage>
        )}

        {activeId === 'advisor' && (
          <SimplePage title="Ask Fin"><AdvisorChat /></SimplePage>
        )}
      </div>
    </div>
  );
}

function SimplePage({ title, children }) {
  return (
    <>
      <div className="eh-topbar">
        <div className="eh-topbar-title">{title}</div>
      </div>
      <div className="eh-content">{children}</div>
    </>
  );
}

// Shared health score calc — also exported via DashboardTab.
function computeHealthScore({ netWorth, trend, creditHealth, monthlyTotals }) {
  let score = 0;
  let weight = 0;

  // Net worth signal (30%)
  const nw = trend?.current_net_worth ?? netWorth;
  if (nw !== null && nw !== undefined) {
    if (trend?.delta_30d !== null && trend?.delta_30d !== undefined) {
      const base = Math.abs(nw) || 1;
      const ratio = trend.delta_30d / base;
      const sub = Math.max(0, Math.min(1, 0.5 + ratio * 5));
      score += sub * 30; weight += 30;
    } else {
      // We have a position but no trend — neutral signal
      const sub = nw >= 0 ? 0.6 : 0.4;
      score += sub * 30; weight += 30;
    }
  }

  // Credit utilization (30%) — only if user has credit cards
  if (creditHealth?.accounts?.length > 0) {
    const u = creditHealth.overall_utilization_pct ?? 0;
    const sub = Math.max(0, 1 - u / 100);
    score += sub * 30; weight += 30;
  }

  // Monthly totals as a savings/expense proxy when income data unavailable.
  // If we have at least one month of spending data, score lower spending higher.
  if (monthlyTotals && monthlyTotals.length >= 2) {
    const last = monthlyTotals[monthlyTotals.length - 1].total || 0;
    const prev = monthlyTotals[monthlyTotals.length - 2].total || 0;
    if (prev > 0) {
      const change = (last - prev) / prev;
      const sub = Math.max(0, Math.min(1, 0.5 - change));
      score += sub * 40; weight += 40;
    }
  }

  if (weight === 0) return null;
  return Math.round((score / weight) * 100);
}
