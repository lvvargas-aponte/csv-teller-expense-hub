import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import FinancesSidebar, { normalizeTabId } from './FinancesSidebar';
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
import PropertiesPage from './PropertiesPage';
import LoansPage from './LoansPage';
import TodayPage from './TodayPage';
import RecurringChargesCard from './cards/RecurringChargesCard';
import UpcomingBillsCard from './cards/UpcomingBillsCard';
import { getDashboard, getCreditHealth } from '../../api/dashboard';
import { getBalancesSummary } from '../../api/balances';
import { computeHealthScore } from '../../utils/healthScore';

const ACTIVE_TAB_KEY = 'finances.activeTab';

export default function FinancesPage() {
  // The active tab now lives in the URL (/finances/:tab) so screens are
  // linkable and the back button works. localStorage is demoted to a hint
  // for a bare /finances, and is remapped through normalizeTabId so a
  // stored legacy id doesn't strand a returning user on a blank shell.
  const { tab } = useParams();
  const navigate = useNavigate();

  const activeId = useMemo(() => {
    if (tab) return normalizeTabId(tab);
    let stored = null;
    try { stored = localStorage.getItem(ACTIVE_TAB_KEY); } catch { /* private mode */ }
    return normalizeTabId(stored);
  }, [tab]);

  // Keep the URL canonical: a bare /finances, an unknown tab, or a legacy id
  // all resolve to a real path rather than lingering as-is.
  useEffect(() => {
    if (tab !== activeId) navigate(`/finances/${activeId}`, { replace: true });
  }, [tab, activeId, navigate]);

  useEffect(() => {
    try { localStorage.setItem(ACTIVE_TAB_KEY, activeId); } catch { /* quota */ }
  }, [activeId]);

  const handleNavigate = useCallback((id) => {
    navigate(`/finances/${id}`);
  }, [navigate]);

  const handleInsightAction = useCallback((target) => {
    if (!target) return;
    if (target.financesTab) navigate(`/finances/${normalizeTabId(target.financesTab)}`);
    else if (target.route)  navigate(target.route);
  }, [navigate]);

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

  return (
    <div className="eh-app">
      <FinancesSidebar
        activeId={activeId}
        onNavigate={handleNavigate}
        healthScore={healthScore}
      />

      <div className="eh-main">
        {activeId === 'today' && <TodayPage />}

        {activeId === 'dashboard' && (
          <DashboardTab healthScore={healthScore} />
        )}

        {activeId === 'accounts' && (
          <SimplePage title="Accounts">
            <AccountsTab
              summary={summary}
              summaryLoading={summaryLoading}
              summaryError={summaryError}
              onRefresh={() => loadBalances(true)}
            />
            <BalancesSection
              summary={summary}
              loading={summaryLoading}
              error={summaryError}
              onRefresh={() => loadBalances(true)}
              onMutate={() => loadBalances(false)}
            />
            <ProfileSection />
          </SimplePage>
        )}

        {activeId === 'spending' && (
          <SimplePage title="Spending">
            <SpendingInsights
              summary={summary}
              dashboard={dashboard}
              onNavigate={handleInsightAction}
            />
          </SimplePage>
        )}

        {activeId === 'investments' && (
          <SimplePage title="Investments"><InvestmentsTab /></SimplePage>
        )}

        {activeId === 'properties' && <PropertiesPage />}

        {activeId === 'loans' && <LoansPage />}

        {activeId === 'budgets' && (
          <SimplePage title="Budgets"><BudgetsSection /></SimplePage>
        )}

        {activeId === 'goals' && (
          <SimplePage title="Goals"><GoalsSection /></SimplePage>
        )}

        {activeId === 'bills' && (
          <SimplePage title="Bills">
            <div style={{ display: 'grid', gap: 16 }}>
              <UpcomingBillsCard onNavigateToAccounts={() => handleNavigate('accounts')} />
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
