import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
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
import AdvisorChat from './AdvisorChat';
import KnowledgeSection from './KnowledgeSection';
import SubscriptionsSection from './SubscriptionsSection';
import SettingsPage from '../settings/SettingsPage';
import useConnectionHealth from './accounts/useConnectionHealth';
import { useCategories } from '../../hooks/useCategories';
import RecurringChargesCard from './cards/RecurringChargesCard';
import UpcomingBillsCard from './cards/UpcomingBillsCard';
import { getDashboard } from '../../api/dashboard';
import { getHealthScore } from '../../api/health';
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
  const [healthData, setHealthData] = useState(null);

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
    getHealthScore().then((r) => setHealthData(r.data)).catch(() => {});
  }, [loadBalances]);

  const healthScore = healthData?.score ?? null;

  const creditAccounts = useMemo(
    () => summary?.accounts?.filter(
      (a) => a.type === 'credit' && Math.abs(parseFloat(a.ledger) || 0) >= 0.005,
    ) ?? [],
    [summary],
  );

  const health = useConnectionHealth(summary?.connections);
  const { categories, counts: categoryCounts } = useCategories();

  // Which settings pane to open — Accounts' connection buttons deep-link
  // straight to "Connected institutions".
  const [settingsPane, setSettingsPane] = useState('profile');
  const openSettings = useCallback((paneId = 'profile') => {
    setSettingsPane(paneId);
    setActiveId('settings');
  }, [setActiveId]);

  // The settings form saves page-wide, so leaving the tab mid-edit would
  // silently drop every pane's changes. No router-level blocker exists on
  // BrowserRouter, so the guard lives on the one nav that can leave.
  const settingsDirtyRef = useRef(false);
  const handleSettingsDirty = useCallback((d) => { settingsDirtyRef.current = d; }, []);
  const handleNavigate = useCallback((id) => {
    if (
      activeId === 'settings' && id !== 'settings' && settingsDirtyRef.current
      // eslint-disable-next-line no-alert
      && !window.confirm('You have unsaved settings. Leave without saving?')
    ) return;
    setActiveId(id);
  }, [activeId, setActiveId]);

  return (
    <div className="eh-app">
      <FinancesSidebar
        activeId={activeId}
        onNavigate={handleNavigate}
        healthScore={healthScore}
        healthSignals={healthData?.signals}
      />

      <div className="eh-main">
        {activeId === 'dashboard' && (
          <DashboardTab healthScore={healthScore} onOpenSettings={openSettings} />
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
            <PayoffPlanner creditAccounts={creditAccounts} />
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
              onManageConnections={() => openSettings('connections')}
            />
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

        {activeId === 'subscriptions' && (
          <SimplePage title="Subscriptions"><SubscriptionsSection /></SimplePage>
        )}

        {activeId === 'knowledge' && (
          <SimplePage title="Knowledge"><KnowledgeSection /></SimplePage>
        )}

        {activeId === 'advisor' && (
          <SimplePage title="Ask Fin"><AdvisorChat /></SimplePage>
        )}

        {activeId === 'settings' && (
          <SimplePage title="Profile & settings">
            <SettingsPage
              initialPane={settingsPane}
              health={health}
              summary={summary}
              categories={categories}
              categoryCounts={categoryCounts}
              onRefreshBalances={() => loadBalances(true)}
              onDirtyChange={handleSettingsDirty}
            />
          </SimplePage>
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
