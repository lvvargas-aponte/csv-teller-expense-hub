import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import FinancesSidebar from './FinancesSidebar';
import DashboardTab from './DashboardTab';
import AccountsTab from './AccountsTab';
import InvestmentsTab from './InvestmentsTab';
import BalancesSection from './BalancesSection';
import PayoffPlanner from './PayoffPlanner';
import CreditFactorsPanel from './CreditFactorsPanel';
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
import { getHealthScore } from '../../api/health';
import { getBalancesSummary } from '../../api/balances';
import { pathForTab } from '../../legacyRoutes';

export default function FinancesPage({ section, view }) {
  const navigate = useNavigate();
  const { pane } = useParams();

  const handleInsightAction = useCallback((target) => {
    if (!target) return;
    if (target.financesTab) navigate(pathForTab(target.financesTab));
    else if (target.route)  navigate(target.route);
  }, [navigate]);

  const openSettings = useCallback(
    (paneId = 'profile') => navigate(`/settings/${paneId}`),
    [navigate],
  );

  // Shared signals used by the sidebar's Financial Health footer.
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [summaryError, setSummaryError] = useState(null);
  const [healthData, setHealthData] = useState(null);

  // Refreshing swaps every number on the page with nothing to hear. One
  // polite region carries the outcome.
  const [announcement, setAnnouncement] = useState('');

  const loadBalances = useCallback((force = false) => {
    setSummaryLoading(true);
    setSummaryError(null);
    setAnnouncement('');
    getBalancesSummary(force)
      .then((r) => {
        setSummary(r.data);
        setAnnouncement('Balances updated');
      })
      .catch(() => {
        setSummaryError('Could not load balances — is the backend running?');
        setAnnouncement('Could not update balances');
      })
      .finally(() => setSummaryLoading(false));
  }, []);

  useEffect(() => {
    loadBalances(false);
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

  // The settings form saves page-wide, so leaving the tab mid-edit would
  // silently drop every pane's changes. No router-level blocker exists on
  // BrowserRouter, so the guard lives on the one nav that can leave.
  const settingsDirtyRef = useRef(false);
  const handleSettingsDirty = useCallback((d) => { settingsDirtyRef.current = d; }, []);
  const handleTabNavigate = useCallback((tabId) => {
    if (
      section === 'settings' && tabId !== 'settings' && settingsDirtyRef.current
      // eslint-disable-next-line no-alert
      && !window.confirm('You have unsaved settings. Leave without saving?')
    ) return;
    navigate(pathForTab(tabId));
  }, [navigate, section]);

  // FinancesSidebar still speaks the pre-Phase-2 tab ids (Task 4 replaces
  // it with a NAV-driven sidebar); translate the route back for its
  // highlight only.
  const sidebarActiveId = section === 'home' ? 'dashboard'
    : section === 'invest' ? 'investments'
    : section === 'plan' ? view
    : section === 'ask' ? 'advisor'
    : section;

  return (
    <div className="eh-app">
      <a className="eh-skip-link" href="#eh-main">Skip to main content</a>
      <FinancesSidebar
        activeId={sidebarActiveId}
        onNavigate={handleTabNavigate}
        healthScore={healthScore}
        healthSignals={healthData?.signals}
      />

      <main className="eh-main" id="eh-main">
        <div className="eh-live-region" role="status" aria-live="polite">
          {announcement}
        </div>
        {section === 'home' && (
          <DashboardTab
            healthScore={healthScore}
            healthSignals={healthData?.signals}
            summary={summary}
            summaryLoading={summaryLoading}
            summaryError={summaryError}
            onOpenSettings={openSettings}
            onNavigate={handleTabNavigate}
            onInsightAction={handleInsightAction}
          />
        )}

        {section === 'accounts' && (
          <SimplePage title="Accounts">
            <AccountsTab
              summary={summary}
              summaryLoading={summaryLoading}
              summaryError={summaryError}
              onRefresh={() => loadBalances(true)}
              onManageConnections={() => openSettings('connections')}
            />
            {/* Manual balances and the payoff planner belong beside the
                accounts they act on, not on a separate Overview page. */}
            <BalancesSection
              summary={summary}
              loading={summaryLoading}
              error={summaryError}
              onRefresh={() => loadBalances(true)}
              onMutate={() => loadBalances(false)}
            />
            <PayoffPlanner creditAccounts={creditAccounts} />
            <CreditFactorsPanel />
          </SimplePage>
        )}

        {section === 'invest' && (
          <SimplePage title="Invest">
            <InvestmentsTab onOpenSettings={openSettings} />
          </SimplePage>
        )}

        {section === 'plan' && view === 'budgets' && (
          <SimplePage title="Budgets"><BudgetsSection /></SimplePage>
        )}

        {section === 'plan' && view === 'goals' && (
          <SimplePage title="Goals"><GoalsSection /></SimplePage>
        )}

        {section === 'plan' && view === 'commitments' && (
          <SimplePage title="Commitments">
            <div style={{ display: 'grid', gap: 16 }}>
              <UpcomingBillsCard onNavigateToAccounts={() => navigate('/accounts')} />
              <RecurringChargesCard variant="detail" />
            </div>
            <SubscriptionsSection />
          </SimplePage>
        )}

        {section === 'ask' && (
          <SimplePage title="Ask">
            <AdvisorChat />
            <KnowledgeSection />
          </SimplePage>
        )}

        {section === 'settings' && (
          <SimplePage title="Profile & settings">
            <SettingsPage
              initialPane={pane || 'profile'}
              health={health}
              summary={summary}
              categories={categories}
              categoryCounts={categoryCounts}
              onRefreshBalances={() => loadBalances(true)}
              onDirtyChange={handleSettingsDirty}
            />
          </SimplePage>
        )}
      </main>
    </div>
  );
}

function SimplePage({ title, children }) {
  return (
    <>
      <div className="eh-topbar">
        <h1 className="eh-topbar-title">{title}</h1>
      </div>
      <div className="eh-content">{children}</div>
    </>
  );
}
